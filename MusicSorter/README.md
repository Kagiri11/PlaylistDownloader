# DJ Music Auto-Sorter

Sorts new tracks in the inbox (`sort_dir`) into genre folders, splitting some
genres into Old School / New School, and cleans filenames to
`Artist (ft Featured) - Title`.

**Extended cuts:** if the word *extended* shows up anywhere in the artist or
title - `(Extended)`, `Extended Mix`, `Extended Version`, `Ext. Mix`, even
buried in YouTube noise like `(Extended - Official Audio)` - the wording is
stripped out and the name ends in a single `[Extended]` tag:

```
44 - Mariah Carey - Never Forget You (Extended - Official Audio).mp3
  -> Mariah Carey - Never Forget You [Extended].mp3
07 - Wizkid ft Tems - Essence (Extended Version) HD.mp3
  -> Wizkid (ft Tems) - Essence [Extended].mp3
```

An extended cut counts as its own song for de-duplication, so it never hides
the original (or gets hidden by it).

## One-time setup
1. **Copy the config and install dependencies:**
   ```
   cp config.example.ini config.ini     # then edit the paths + keys
   python3 -m pip install -r requirements.txt
   sudo apt install ffmpeg              # provides ffprobe
   ```
   `config.ini` holds your API keys, so it is git-ignored - keep it local.
2. **Get free API keys** and paste them into `config.ini` under `[api]`:
   - **Spotify**: https://developer.spotify.com/dashboard → *Create app* →
     copy **Client ID** and **Client secret**. (Redirect URI can be anything,
     e.g. `http://localhost` — we never log in as a user.)
   - **Last.fm**: https://www.last.fm/api/account/create → copy the **API key**.
   - **MusicBrainz**: no key needed; just put a real email in the User-Agent line.

   It still runs without keys, but genre/year accuracy drops a lot.

## Everyday use
- **See what it WOULD do (safe):** `./run_dryrun.sh`, then open the newest
  `logs/report_*.csv`. Nothing is moved.
- **Actually sort:** `./run_sort.sh`. It first moves everything from `intake_dir`
  (`~/Music` - including the per-playlist subfolders the downloader creates)
  into the inbox, then files each song into its genre folder. Low-confidence
  songs go to `<sort_dir>/_Review/` (nothing is lost).
- **Run daily automatically:** a cron line, e.g. 3:00 AM:
  ```
  0 3 * * * "/media/charles/Cap10/To Sort/PlaylistDownloader/MusicSorter/run_sort.sh" >/dev/null 2>&1
  ```

The old Windows runners (`*.bat`, `register_task.ps1`) are not carried over;
`run_*.sh` replaces them.

## Tuning
Open `genre_rules.py`:
- `ERA_CUTOFFS` — the Old/New School pivot years.
- `TAG_RULES` — which online tags map to which folder.
- Region overrides (Kenya/Tanzania/Congo/Jamaica) live in `classify()`.

`config.ini → confidence_threshold` controls how sure it must be before
auto-filing (lower = more files filed, more mistakes; higher = more go to _Review).

## Avoiding duplicates
The sorter remembers every song it files (in a `sorted` table inside `cache.sqlite`).
If the **same song** shows up again it is moved to **`<sort_dir>/Ignored`** instead of a
genre folder — nothing is deleted, you confirm/clear it yourself. "Same song" means same
artist+title AND length within `duplicate_tolerance_seconds` (default 10s), so different
edits/remixes are kept.

Seed it once from the music you've already sorted:
```
python3 sort_music.py --reindex
```
This indexes the genre folders under `library_dir` so re-downloads of those are caught straight
away. Only confidently-identified songs are de-duplicated; `_Review` items are never
treated as duplicates.

## Artist rosters (placement correction)
Each genre folder has a living **`_artists.txt`** listing the artists expected there.
Each file has two parts. **Lines above the `# --- auto-added ---` marker are yours**
(curated, "manual") and are **trusted completely** — a manual match always overrides the
tag-based guess, so local artists (Genge, Bongo, etc.) stop being mislabelled as Hip Hop/Pop.
Lines **below** the marker are machine-added ("auto") and treated cautiously: an auto match
only rescues a song the tag guess left uncertain (would-be `_Review`); it never overrides a
confident genre call, and `--reconcile` ignores auto entries entirely. **Move artists you
trust ABOVE the marker** — that's where hand-curation pays off.

- **Seed them once:** `python3 sort_music.py --seed-rosters` (pulls each scene's artists from
  Last.fm + your starter lists). Then hand-add any locals the charts miss.
- **Fix already-sorted music:** `run_reconcile.sh` (or `python3 sort_music.py --reconcile`)
  shows which filed songs are in the wrong folder per the rosters → `reconcile_*.csv`,
  moves nothing. Apply with `python3 sort_music.py --reconcile --apply`. (Reconcile only fixes
  the *scene*, never Old/New era, since it has no reliable year.)
- **Grow them:** `run_update.sh` / `python3 sort_music.py --update-rosters` expands each list
  with related/similar/expected artists and learns from new placements. Worth a weekly cron line of its own.

Turn the whole feature off with `[rosters] enabled = false` in config.ini.

## Notes
- Cache (`cache.sqlite`) makes re-runs instant and respects API rate limits.
  Delete it to force fresh lookups, or run with `--no-cache`.
- `--limit N` processes only the first N files (handy for testing).
