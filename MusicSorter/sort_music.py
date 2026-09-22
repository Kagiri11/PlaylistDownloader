"""
sort_music.py  -  DJ Music Auto-Sorter
======================================
Run modes:
    python sort_music.py            # DRY-RUN: writes a CSV report, moves nothing
    python sort_music.py --apply    # REAL: intake-move, then sort + rename files
    python sort_music.py --apply --no-cache   # ignore cached lookups
    python sort_music.py --limit 10           # only process first N (testing)

Pipeline per file: parse name -> read embedded tags -> online lookup
(Spotify/Last.fm/MusicBrainz) -> map to your genre folder -> decide Old/New ->
build a clean "Artist (ft Featured) - Title" name -> report or move.

Extended cuts (the word "extended" anywhere in the artist or title) keep that
fact in one canonical place: the name ends "... - Title [Extended]".
"""

import argparse
import configparser
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

import genre_rules
import dedupe
import roster
from lookup import Lookup

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
# Broad global buckets where local artists get mislabelled; an 'auto' roster
# entry may rescue songs from these, but won't override a confident scene call.
GLOBAL_BUCKETS = {"Hip Hop", "Pop", "RnB", "EDM", "House", "Trap", "Gospel", "Unknown"}

# Tokens that mark a bracketed/loose chunk as YouTube noise to delete.
NOISE = [
    "official", "video", "audio", "lyric", "lyrics", "visualizer", "visualiser",
    "hd", "hq", "4k", "sd", "mv", "music video", "official music video",
    "radio edit", "radio", "full length", "full video", "full song", "clean",
    "dirty", "explicit", "remaster", "remastered", "prod", "exclusive",
    "official video", "official audio", "official lyric video", "lyric video",
    "432 hz", "432hz", "high quality", "youtube", "out now", "audio only",
]
FEAT_RE = re.compile(r"\b(?:feat|ft|featuring|f)\.?\s+(.+?)(?=[\)\]\|]| - |$)",
                     re.IGNORECASE)
# "Extended", "Extended Mix/Version/Edit/...", "Ext. Mix" - however the upload
# spelled it, we drop the words and re-add a single "[Extended]" tag instead.
EXTENDED_RE = re.compile(
    r"\b(?:extended(?:\s+(?:club\s+)?(?:mix|version|edit|re-?edit|cut|remix|play))?"
    r"|ext\.?\s+(?:mix|version|edit))\b",
    re.IGNORECASE,
)
LEAD_TRACKNO_RE = re.compile(r"^\s*\d{1,3}\s*[-.\)]\s*")
ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')

FULLWIDTH = {"＂": '"', "｜": "|", "？": "?", "：": ":", "／": "/", "＊": "*"}


def fold_fullwidth(s):
    for k, v in FULLWIDTH.items():
        s = s.replace(k, v)
    return s


def strip_extended(s):
    """Return (text without any 'extended' wording, was_extended)."""
    if not s:
        return s, False
    cleaned, n = EXTENDED_RE.subn(" ", s)
    if not n:
        return s, False
    # tidy up what the removal left behind: "()", "[]", doubled spaces/dashes
    cleaned = re.sub(r"[\(\[]\s*[-,]?\s*[\)\]]", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -|·."), True


def strip_noise_chunks(s):
    """Remove (...) / [...] chunks that are clearly YouTube noise."""
    def drop(m):
        inner = m.group(1).lower()
        return "" if any(n in inner for n in NOISE) else m.group(0)
    s = re.sub(r"\(([^()]*)\)", drop, s)
    s = re.sub(r"\[([^\[\]]*)\]", drop, s)
    # loose trailing noise words and @handles
    s = re.sub(r"@\S+", "", s)
    for n in sorted(NOISE, key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(n)}\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" -|·.")


def parse_filename(filename):
    """Return dict(artist, title, featured[list], extended) from a messy name."""
    stem = os.path.splitext(filename)[0]
    stem = fold_fullwidth(stem)
    stem = stem.replace(".mp4", "").replace(" - YouTube", "")
    stem = LEAD_TRACKNO_RE.sub("", stem)
    # Before the noise pass: "(Extended - Official Audio)" would otherwise be
    # thrown away whole, taking the one word we care about with it.
    stem, extended = strip_extended(stem)

    featured = []
    for m in FEAT_RE.finditer(stem):
        names = re.split(r"[,&]| and | x ", m.group(1))
        featured += [n.strip() for n in names if n.strip()]
    # remove the feat clause from the working string
    stem = FEAT_RE.sub("", stem)
    # drop any now-empty () or [] left behind by the feat removal
    stem = re.sub(r"[\(\[]\s*[\)\]]", " ", stem)

    stem = strip_noise_chunks(stem)

    artist, title = None, stem
    if " - " in stem:
        left, right = stem.split(" - ", 1)
        artist, title = left.strip(), right.strip()
    title = title.strip(" -|·.")
    # de-dup featured, drop ones already equal to artist
    seen, feat = set(), []
    for f in featured:
        fl = f.lower()
        if fl and fl not in seen and fl != (artist or "").lower():
            seen.add(fl)
            feat.append(f)
    return {"artist": artist or None, "title": title or stem, "featured": feat,
            "extended": extended}


def read_embedded_tags(path, ffprobe):
    """Use ffprobe to pull artist/title/date/genre from container tags."""
    out = {"artist": None, "title": None, "year": None, "genre": None,
           "duration": None}
    if not ffprobe or not os.path.exists(ffprobe):
        return out
    try:
        r = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        fmt = json.loads(r.stdout or "{}").get("format", {}) or {}
        try:
            out["duration"] = float(fmt.get("duration"))
        except (TypeError, ValueError):
            pass
        tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
        out["artist"] = tags.get("artist") or tags.get("album_artist")
        out["title"] = tags.get("title")
        out["genre"] = tags.get("genre")
        d = tags.get("date") or tags.get("year") or ""
        m = re.match(r"(\d{4})", str(d))
        if m:
            out["year"] = int(m.group(1))
    except Exception:
        pass
    return out


def read_duration(path, ffprobe):
    """Just the track length in seconds (used by --reindex)."""
    return read_embedded_tags(path, ffprobe).get("duration")


def sanitize(name):
    name = ILLEGAL_RE.sub("", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" .")
    return name[:180] if len(name) > 180 else name


def build_clean_name(meta, parsed, ext):
    """Format: 'Artist (ft A, B) - Title', plus ' [Extended]' for extended cuts."""
    artist = meta.get("artist") or parsed.get("artist")
    title = meta.get("title") or parsed.get("title") or "Unknown Title"
    # The online title can carry the wording too ("Never Forget You - Extended").
    artist, a_ext = strip_extended(artist)
    title, t_ext = strip_extended(title)
    extended = bool(parsed.get("extended") or meta.get("extended")
                    or a_ext or t_ext)
    title = title or "Unknown Title"
    featured = meta.get("featured") or parsed.get("featured") or []
    feat = ", ".join(featured)
    if artist:
        core = f"{artist} (ft {feat}) - {title}" if feat else f"{artist} - {title}"
    else:
        core = f"{title} (ft {feat})" if feat else title
    # Tag goes on after sanitising so the length cap can never clip it off.
    return sanitize(core) + (" [Extended]" if extended else "") + ext.lower()


def unique_path(folder, filename):
    target = os.path.join(folder, filename)
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(filename)
    i = 2
    while True:
        cand = os.path.join(folder, f"{stem} ({i}){ext}")
        if not os.path.exists(cand):
            return cand
        i += 1


def intake_move(intake_dir, sort_dir, log):
    if not os.path.isdir(intake_dir):
        log(f"[intake] folder not found, skipping: {intake_dir}")
        return 0
    os.makedirs(sort_dir, exist_ok=True)
    moved = 0
    # The playlist downloader files each playlist in its own subfolder, so walk.
    for root, _dirs, entries in os.walk(intake_dir):
        for entry in entries:
            src = os.path.join(root, entry)
            if not os.path.isfile(src):
                continue
            shutil.move(src, unique_path(sort_dir, entry))
            moved += 1
    for root, dirs, _entries in os.walk(intake_dir, topdown=False):
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))      # only removes empty ones
            except OSError:
                pass
    log(f"[intake] moved {moved} file(s) from {intake_dir} -> {sort_dir}")
    return moved


def list_media(folder, include_video, recursive=False):
    """Media directly in `folder`, or anywhere under it when recursive.

    The inbox is listed flat on purpose: recursing there would re-process
    everything sitting in _Review and Ignored. The intake folder IS recursed,
    because the playlist downloader nests one folder per playlist.
    """
    if not os.path.isdir(folder):
        return []
    exts = AUDIO_EXT | (VIDEO_EXT if include_video else set())
    files = []
    if recursive:
        for root, _dirs, entries in os.walk(folder):
            for entry in sorted(entries):
                p = os.path.join(root, entry)
                if os.path.splitext(entry)[1].lower() in exts:
                    files.append(p)
        return sorted(files)
    for entry in sorted(os.listdir(folder)):
        p = os.path.join(folder, entry)
        if os.path.isfile(p) and os.path.splitext(entry)[1].lower() in exts:
            files.append(p)
    return files


def _folder_artists(library_dir, folder):
    """Parsed artist names of the media currently filed in a genre folder."""
    out = []
    folder_path = os.path.join(library_dir, folder)
    if not os.path.isdir(folder_path):
        return out
    for entry in os.listdir(folder_path):
        if entry == roster.ROSTER_FILE:
            continue
        if os.path.isfile(os.path.join(folder_path, entry)):
            a = parse_filename(entry).get("artist")
            if a:
                out.append(a)
    return out


def seed_rosters(store, lk, cfg, log):
    top_n = cfg.getint("rosters", "tag_top_artists", fallback=40)
    for folder, spec in roster.SEED.items():
        store.seed_folder(folder, spec["seeds"])          # curated -> manual
        chart = []
        for tag in spec["tags"]:
            chart += lk.lastfm_tag_top_artists(tag, top_n)
        store.add_auto(folder, chart)                     # chart -> auto
        log(f"[seed] {folder}: {len(spec['seeds'])} seeds + {len(set(chart))} chart")


def update_rosters(store, lk, cfg, library_dir, genre_folders, log):
    top_n = cfg.getint("rosters", "tag_top_artists", fallback=40)
    rel_n = cfg.getint("rosters", "related_per_artist", fallback=10)
    store.load(genre_folders)
    for folder, spec in roster.SEED.items():
        manual, _ = store.read_file(folder)
        manual_names = [s for s in (ln.strip() for ln in manual)
                        if s and not s.startswith("#")]
        found = []
        for tag in spec["tags"]:
            found += lk.lastfm_tag_top_artists(tag, top_n)
        for a in manual_names:
            found += lk.lastfm_similar_artists(a, rel_n)
            aid = lk.spotify_artist_id(a)
            if aid:
                found += lk.spotify_related_artists(aid, rel_n)
        found += _folder_artists(library_dir, folder)     # learn from placements
        store.add_auto(folder, found)
        log(f"[update] {folder}: +{len(set(found))} candidate(s)")


def reconcile(store, library_dir, genre_folders, ffprobe, apply, log,
              logs_dir, stamp):
    store.load(genre_folders)
    moves = []
    for folder in genre_folders:
        folder_path = os.path.join(library_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        for entry in sorted(os.listdir(folder_path)):
            if entry == roster.ROSTER_FILE:
                continue
            p = os.path.join(folder_path, entry)
            if not os.path.isfile(p):
                continue
            artist = parse_filename(entry).get("artist")
            pre = store.folder_for_artist(artist, None)      # cheap pre-check
            # Reconcile is destructive, so only act on curated 'manual' entries.
            if not pre or pre[1] != "manual":
                continue
            year = read_embedded_tags(p, ffprobe).get("year")
            target = store.folder_for_artist(artist, year)[0]
            if target == folder:
                continue
            # Don't flip Old<->New of the SAME scene here: reconcile has no
            # reliable year, so leave era alone and only fix scene mistakes.
            if roster.ERA_FOLDERS.get(folder, folder) == \
               roster.ERA_FOLDERS.get(target, target):
                continue
            moves.append((folder, entry, target, artist))
            log(f"[reconcile] {folder}/{entry}  ->  {target}  ({artist})")
            if apply:
                out_dir = os.path.join(library_dir, target)
                os.makedirs(out_dir, exist_ok=True)
                shutil.move(p, unique_path(out_dir, entry))
    report = os.path.join(logs_dir, f"reconcile_{stamp}.csv")
    with open(report, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["from_folder", "file", "to_folder", "artist"])
        w.writerows(moves)
    log(f"{'Moved' if apply else 'Would move'} {len(moves)} file(s). Report: {report}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually move/rename (default is a dry-run report)")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore cached online lookups")
    ap.add_argument("--limit", type=int, default=0,
                    help="process only the first N files (testing)")
    ap.add_argument("--reindex", action="store_true",
                    help="seed the duplicate DB from existing genre folders, then exit")
    ap.add_argument("--seed-rosters", action="store_true",
                    help="create per-folder _artists.txt from seeds + Last.fm charts")
    ap.add_argument("--update-rosters", action="store_true",
                    help="expand rosters with related/similar/expected artists")
    ap.add_argument("--reconcile", action="store_true",
                    help="re-check sorted folders against rosters; --apply to move misfits")
    args = ap.parse_args()
    dry = not args.apply

    try:                       # make the console tolerate unicode filenames
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(HERE, "config.ini"), encoding="utf-8")
    intake_dir = cfg.get("paths", "intake_dir")
    sort_dir = cfg.get("paths", "sort_dir")
    # Genre folders live here (siblings of the inbox). Default: inbox's parent.
    library_dir = cfg.get("paths", "library_dir",
                          fallback=os.path.dirname(os.path.normpath(sort_dir)))
    ffprobe = cfg.get("paths", "ffprobe", fallback="")
    threshold = cfg.getint("settings", "confidence_threshold", fallback=2)
    include_video = cfg.getboolean("settings", "include_video", fallback=True)
    dup_tol = cfg.getfloat("settings", "duplicate_tolerance_seconds", fallback=10)
    rosters_on = cfg.getboolean("rosters", "enabled", fallback=True)
    idx = dedupe.SortedIndex(os.path.join(HERE, "cache.sqlite"))
    store = roster.RosterStore(library_dir)

    logs_dir = os.path.join(HERE, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    log_path = os.path.join(logs_dir, f"run_{stamp}.log")
    logf = open(log_path, "a", encoding="utf-8")

    def log(msg):
        line = f"{dt.datetime.now():%H:%M:%S} {msg}"
        print(line)
        logf.write(line + "\n")
        logf.flush()

    log(f"=== DJ Music Sorter ({'APPLY' if args.apply else 'DRY-RUN'}) ===")

    if args.reindex:
        n = idx.reindex(library_dir, genre_rules.GENRE_FOLDERS,
                        parse_filename, lambda p: read_duration(p, ffprobe))
        log(f"Re-index complete: added {n} song(s); "
            f"DB now holds {idx.count()} record(s).")
        logf.close()
        return

    lk = Lookup(cfg, os.path.join(HERE, "cache.sqlite"))

    if args.reconcile:
        reconcile(store, library_dir, genre_rules.GENRE_FOLDERS, ffprobe,
                  args.apply, log, logs_dir, stamp)
        logf.close()
        return
    if args.seed_rosters:
        seed_rosters(store, lk, cfg, log)
        logf.close()
        return
    if args.update_rosters:
        update_rosters(store, lk, cfg, library_dir, genre_rules.GENRE_FOLDERS, log)
        logf.close()
        return

    if rosters_on:
        store.load(genre_rules.GENRE_FOLDERS)

    if not (lk.sp_id and lk.sp_secret):
        log("[warn] Spotify keys missing - genre/year accuracy will be low.")
    if not lk.lfm_key:
        log("[warn] Last.fm key missing - fewer genre tags.")

    # Step 0: intake. In dry-run we DON'T move; we just also scan the intake dir.
    if args.apply:
        # Pre-create the full set of genre folders so they always exist.
        for g in genre_rules.GENRE_FOLDERS:
            if g != "Unknown":
                os.makedirs(os.path.join(library_dir, g), exist_ok=True)
        intake_move(intake_dir, sort_dir, log)
        files = list_media(sort_dir, include_video)
    else:
        files = list_media(sort_dir, include_video) + \
                list_media(intake_dir, include_video, recursive=True)

    if args.limit:
        files = files[:args.limit]
    log(f"Processing {len(files)} file(s).")

    report_rows = []
    counts = {}
    for i, path in enumerate(files, 1):
        fn = os.path.basename(path)
        parsed = parse_filename(fn)
        id3 = read_embedded_tags(path, ffprobe)
        # Tags can spell it out too; strip the wording before the lookup (the
        # services know "Never Forget You", not "Never Forget You Extended").
        artist, a_ext = strip_extended(parsed["artist"] or id3["artist"])
        title, t_ext = strip_extended(parsed["title"] or id3["title"])
        if a_ext or t_ext:
            parsed["extended"] = True

        meta = lk.resolve(
            artist, title,
            id3_tags=[id3["genre"]] if id3["genre"] else None,
            id3_year=id3["year"],
            use_cache=not args.no_cache,
        )
        # carry parsed featured if online didn't supply any
        if not meta.get("featured") and parsed["featured"]:
            meta["featured"] = parsed["featured"]

        folder, conf, reason = genre_rules.classify(meta)
        # roster override: a known artist's folder beats the generic tag guess.
        # 'manual' (curated) always wins; 'auto' (machine-added, noisier) only
        # rescues songs the tag guess left weak or in a broad global bucket.
        if rosters_on:
            rf = store.folder_for_artist(meta.get("artist") or artist,
                                         meta.get("year"))
            if rf:
                rfolder, rsrc = rf
                # manual always wins; auto only rescues songs the tag guess left
                # weak (headed to _Review) - it never overrides a confident call.
                weak = conf < threshold or folder == "Unknown"
                if rsrc == "manual" or weak:
                    folder = rfolder
                    reason = f"roster-{rsrc}:{meta.get('artist') or artist}"
                    conf = max(conf, threshold)
        low = conf < threshold
        dest_folder = "_Review" if (low or folder == "Unknown") else folder
        new_name = build_clean_name(meta, parsed, os.path.splitext(fn)[1])

        # --- duplicate check (only for confidently identified songs) ---
        # _Review items have unreliable identity, so we never call them dupes.
        akey, duration = None, id3.get("duration")
        if dest_folder != "_Review":
            # Key off the clean name (same parse the seeding uses), so a song and
            # its already-filed copy produce an identical key.
            pk = parse_filename(new_name)
            akey = dedupe.make_key(pk["artist"], pk["title"], pk["extended"])
            if idx.seen(akey, duration, dup_tol):
                dest_folder = "Ignored"
                reason = f"duplicate of already-sorted ({folder})"
            else:
                idx.remember_run(akey, duration)

        counts[dest_folder] = counts.get(dest_folder, 0) + 1
        report_rows.append({
            "old_name": fn,
            "new_name": new_name,
            "destination": dest_folder,
            "detected_genre": folder,
            "confidence": conf,
            "artist": meta.get("artist") or "",
            "title": meta.get("title") or "",
            "featured": ", ".join(meta.get("featured") or []),
            "extended": "yes" if new_name.endswith(f"[Extended]{os.path.splitext(fn)[1].lower()}") else "",
            "year": meta.get("year") or "",
            "region": meta.get("region") or "",
            "tags": ", ".join(meta.get("tags") or []),
            "sources": ", ".join(meta.get("sources") or []),
            "reason": reason,
        })
        log(f"[{i}/{len(files)}] {fn}  ->  {dest_folder}/{new_name}  "
            f"(conf {conf})")

        if args.apply:
            # _Review and Ignored stay inside the inbox; genres go to the root.
            base = sort_dir if dest_folder in ("_Review", "Ignored") else library_dir
            out_dir = os.path.join(base, dest_folder)
            os.makedirs(out_dir, exist_ok=True)
            final = unique_path(out_dir, new_name)
            shutil.move(path, final)
            # remember songs we actually filed into a genre folder
            if dest_folder not in ("_Review", "Ignored") and akey:
                idx.add(akey, duration, meta.get("artist"), meta.get("title"),
                        dest_folder, os.path.basename(final))

    # write CSV report
    report_path = os.path.join(logs_dir, f"report_{stamp}.csv")
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        cols = ["old_name", "new_name", "destination", "detected_genre",
                "confidence", "artist", "title", "featured", "extended", "year",
                "region", "tags", "sources", "reason"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(report_rows)

    log("--- summary ---")
    for k in sorted(counts):
        log(f"  {k}: {counts[k]}")
    log(f"Report: {report_path}")
    if dry:
        log("DRY-RUN complete. No files were moved. "
            "Review the CSV, then run with --apply.")
    logf.close()


if __name__ == "__main__":
    main()
