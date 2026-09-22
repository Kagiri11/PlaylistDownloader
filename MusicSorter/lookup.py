"""
lookup.py
=========
Resolves a song (artist + title guess) into clean metadata by querying, in order:

  * Spotify        -> canonical artist/title, featured artists, release year,
                      artist genres
  * Last.fm        -> community genre tags for the track (then the artist)
  * MusicBrainz    -> artist country (region) + earliest release year

Everything is cached in cache.sqlite keyed by the normalised "artist|title", so
repeat/daily runs are instant and we stay inside the free rate limits.

Each client fails soft: a missing API key or a network hiccup just means that
source contributes nothing, the others still run.
"""

import base64
import json
import os
import re
import sqlite3
import time
import requests

_MB_MIN_INTERVAL = 1.1          # MusicBrainz asks for <= 1 request/second
_mb_last_call = 0.0


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# Useless tags that carry no genre signal - dropped before classifying.
GENERIC_TAGS = {
    "music", "song", "songs", "seen live", "spotify", "favorites",
    "favourites", "favorite songs", "favourite songs", "love", "awesome",
    "good music", "00s", "10s", "20s", "90s", "80s", "70s", "all", "audio",
    "video", "official", "youtube", "my music", "beautiful", "cool",
    "people & blogs", "entertainment", "lesser known yet streamable artists",
    "lesser known artists", "post-punk",
}


class Cache:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS lookups (key TEXT PRIMARY KEY, data TEXT)"
        )
        self.db.commit()

    def get(self, key):
        row = self.db.execute(
            "SELECT data FROM lookups WHERE key=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, data):
        self.db.execute(
            "INSERT OR REPLACE INTO lookups (key, data) VALUES (?,?)",
            (key, json.dumps(data)),
        )
        self.db.commit()


class Lookup:
    def __init__(self, cfg, cache_path):
        self.cfg = cfg
        self.cache = Cache(cache_path)
        self.sp_id = cfg.get("api", "spotify_client_id", fallback="").strip()
        self.sp_secret = cfg.get("api", "spotify_client_secret", fallback="").strip()
        self.lfm_key = cfg.get("api", "lastfm_api_key", fallback="").strip()
        self.mb_ua = cfg.get("api", "musicbrainz_user_agent",
                             fallback="DJMusicSorter/1.0").strip()
        self._sp_token = None
        self._sp_token_exp = 0

    # ---------------------------------------------------------------- Spotify
    def _spotify_token(self):
        if not (self.sp_id and self.sp_secret):
            return None
        if self._sp_token and time.time() < self._sp_token_exp - 30:
            return self._sp_token
        try:
            auth = base64.b64encode(
                f"{self.sp_id}:{self.sp_secret}".encode()).decode()
            r = requests.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {auth}"},
                timeout=15,
            )
            r.raise_for_status()
            j = r.json()
            self._sp_token = j["access_token"]
            self._sp_token_exp = time.time() + j.get("expires_in", 3600)
            return self._sp_token
        except Exception:
            return None

    def _spotify(self, artist, title, out):
        token = self._spotify_token()
        if not token:
            return
        try:
            q = f'track:"{title}"'
            if artist:
                q += f' artist:"{artist}"'
            r = requests.get(
                "https://api.spotify.com/v1/search",
                params={"q": q, "type": "track", "limit": 5},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            r.raise_for_status()
            items = r.json().get("tracks", {}).get("items", [])
            if not items and artist:        # retry looser, title only
                r = requests.get(
                    "https://api.spotify.com/v1/search",
                    params={"q": title, "type": "track", "limit": 5},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                r.raise_for_status()
                items = r.json().get("tracks", {}).get("items", [])
            if not items:
                return
            tr = items[0]
            arts = tr.get("artists", [])
            if arts:
                out["artist"] = arts[0]["name"]
                out["featured"] = [a["name"] for a in arts[1:]]
            out["title"] = tr.get("name") or out.get("title")
            rd = (tr.get("album") or {}).get("release_date", "")
            m = re.match(r"(\d{4})", rd or "")
            if m:
                out["year"] = int(m.group(1))
            # genres live on the artist object
            if arts:
                aid = arts[0]["id"]
                out["artist_id"] = aid
                ar = requests.get(
                    f"https://api.spotify.com/v1/artists/{aid}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                if ar.ok:
                    genres = ar.json().get("genres", []) or []
                    if genres:
                        out["spotify_had_genres"] = True
                        out["tags"].extend(g.lower() for g in genres)
            out["sources"].append("spotify")
        except Exception:
            return

    # ---------------------------------------------------------------- Last.fm
    def _lastfm(self, artist, title, out):
        if not self.lfm_key:
            return
        a = out.get("artist") or artist
        t = out.get("title") or title
        if not a:
            return
        try:
            def gettags(method, params):
                params.update({"method": method, "api_key": self.lfm_key,
                               "format": "json", "autocorrect": 1})
                r = requests.get("http://ws.audioscrobbler.com/2.0/",
                                 params=params, timeout=15)
                if not r.ok:
                    return []
                tags = r.json().get("toptags", {}).get("tag", [])
                return [tg["name"].lower() for tg in tags
                        if int(tg.get("count", 0)) >= 10][:8]

            got = gettags("track.gettoptags", {"artist": a, "track": t}) if t else []
            if not got:
                got = gettags("artist.gettoptags", {"artist": a})
            if got:
                out["tags"].extend(got)
                out["sources"].append("lastfm")
        except Exception:
            return

    # ------------------------------------------------------------ MusicBrainz
    def _musicbrainz(self, artist, title, out):
        global _mb_last_call

        def throttle():
            global _mb_last_call
            wait = _MB_MIN_INTERVAL - (time.time() - _mb_last_call)
            if wait > 0:
                time.sleep(wait)
            _mb_last_call = time.time()

        a = out.get("artist") or artist
        t = out.get("title") or title
        if not t:
            return
        headers = {"User-Agent": self.mb_ua}
        try:
            query = f'recording:"{t}"'
            if a:
                query += f' AND artist:"{a}"'
            throttle()
            r = requests.get(
                "https://musicbrainz.org/ws/2/recording",
                params={"query": query, "fmt": "json", "limit": 3},
                headers=headers, timeout=20,
            )
            if not r.ok:
                return
            recs = r.json().get("recordings", [])
            if not recs:
                return
            rec = recs[0]
            frd = rec.get("first-release-date", "")
            m = re.match(r"(\d{4})", frd or "")
            if m and not out.get("year"):
                out["year"] = int(m.group(1))
            credit = rec.get("artist-credit", [])
            if credit:
                art = credit[0].get("artist", {})
                aid = art.get("id")
                if aid:
                    throttle()
                    ar = requests.get(
                        f"https://musicbrainz.org/ws/2/artist/{aid}",
                        params={"fmt": "json"}, headers=headers, timeout=20,
                    )
                    if ar.ok:
                        aj = ar.json()
                        country = aj.get("country") or (
                            aj.get("area", {}) or {}).get("iso-3166-1-codes", [None])[0]
                        if country:
                            out["region"] = country
            out["sources"].append("musicbrainz")
        except Exception:
            return

    # ----------------------------------------------- artist discovery (rosters)
    def spotify_artist_id(self, artist):
        token = self._spotify_token()
        if not (token and artist):
            return None
        try:
            r = requests.get(
                "https://api.spotify.com/v1/search",
                params={"q": artist, "type": "artist", "limit": 1},
                headers={"Authorization": f"Bearer {token}"}, timeout=15)
            items = r.json().get("artists", {}).get("items", []) if r.ok else []
            return items[0]["id"] if items else None
        except Exception:
            return None

    def spotify_related_artists(self, artist_id, limit=10):
        token = self._spotify_token()
        if not (token and artist_id):
            return []
        try:
            r = requests.get(
                f"https://api.spotify.com/v1/artists/{artist_id}/related-artists",
                headers={"Authorization": f"Bearer {token}"}, timeout=15)
            arts = r.json().get("artists", []) if r.ok else []
            return [a["name"] for a in arts[:limit]]
        except Exception:
            return []

    def lastfm_tag_top_artists(self, tag, limit=40):
        if not self.lfm_key:
            return []
        try:
            r = requests.get("http://ws.audioscrobbler.com/2.0/", timeout=15,
                             params={"method": "tag.gettopartists", "tag": tag,
                                     "api_key": self.lfm_key, "format": "json",
                                     "limit": limit})
            arts = r.json().get("topartists", {}).get("artist", []) if r.ok else []
            return [a["name"] for a in arts]
        except Exception:
            return []

    def lastfm_similar_artists(self, artist, limit=20):
        if not (self.lfm_key and artist):
            return []
        try:
            r = requests.get("http://ws.audioscrobbler.com/2.0/", timeout=15,
                             params={"method": "artist.getsimilar", "artist": artist,
                                     "api_key": self.lfm_key, "format": "json",
                                     "autocorrect": 1, "limit": limit})
            arts = r.json().get("similarartists", {}).get("artist", []) if r.ok else []
            return [a["name"] for a in arts]
        except Exception:
            return []

    # ------------------------------------------------------------------ main
    def resolve(self, artist, title, id3_tags=None, id3_year=None,
                use_cache=True):
        key = f"{_norm(artist)}|{_norm(title)}"
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        out = {
            "artist": artist, "featured": [], "title": title,
            "year": id3_year, "region": None, "tags": [],
            "spotify_had_genres": False, "artist_id": None, "sources": [],
        }
        if id3_tags:
            out["tags"].extend(t.lower() for t in id3_tags)

        self._spotify(artist, title, out)
        self._lastfm(artist, title, out)
        self._musicbrainz(artist, title, out)

        # de-dup tags, drop generic junk, keep order
        seen, deduped = set(), []
        for t in out["tags"]:
            t = t.strip()
            if t and t not in seen and t not in GENERIC_TAGS:
                seen.add(t)
                deduped.append(t)
        out["tags"] = deduped

        self.cache.put(key, out)
        return out
