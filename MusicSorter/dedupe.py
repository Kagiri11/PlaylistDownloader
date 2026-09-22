"""
dedupe.py
=========
Remembers songs the sorter has already filed, so the same track downloaded again
isn't re-filed into a genre folder (it goes to the Ignored folder instead).

A "duplicate" = same canonical artist+title AND track length within a tolerance
(default 10s), so radio edits / extended mixes / remixes of the same title are
KEPT as separate songs.

Records live in a `sorted` table inside the same cache.sqlite the lookup cache
uses. An in-memory set also catches duplicates that appear twice within a single
run (works in dry-run too, where nothing is written to the DB).
"""

import datetime as dt
import os
import sqlite3

from lookup import _norm   # reuse the same normalisation as the lookup cache


def make_key(artist, title, extended=False):
    """Canonical identity of a song. An extended cut is its own song, so the
    flag is part of the key - otherwise it would shadow the original."""
    return f"{_norm(artist)}|{_norm(title)}" + ("|extended" if extended else "")


class SortedIndex:
    def __init__(self, db_path):
        self.db = sqlite3.connect(db_path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sorted ("
            "akey TEXT, duration REAL, artist TEXT, title TEXT, "
            "genre TEXT, final_name TEXT, sorted_at TEXT)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sorted_akey ON sorted(akey)"
        )
        self.db.commit()
        self._run = {}      # akey -> list[duration|None] seen this run

    @staticmethod
    def _dur_match(d1, d2, tol):
        """Same song if either duration is unknown, else within tolerance."""
        if d1 is None or d2 is None:
            return True
        return abs(d1 - d2) <= tol

    def _stored_durations(self, akey):
        rows = self.db.execute(
            "SELECT duration FROM sorted WHERE akey=?", (akey,)
        ).fetchall()
        return [r[0] for r in rows]

    def seen(self, akey, duration, tol):
        """True if this akey+duration was filed before (DB) or earlier this run."""
        for d in self._stored_durations(akey):
            if self._dur_match(duration, d, tol):
                return True
        for d in self._run.get(akey, []):
            if self._dur_match(duration, d, tol):
                return True
        return False

    def remember_run(self, akey, duration):
        self._run.setdefault(akey, []).append(duration)

    def add(self, akey, duration, artist, title, genre, final_name):
        self.db.execute(
            "INSERT INTO sorted (akey, duration, artist, title, genre, "
            "final_name, sorted_at) VALUES (?,?,?,?,?,?,?)",
            (akey, duration, artist or "", title or "", genre, final_name,
             dt.datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM sorted").fetchone()[0]

    def reindex(self, library_dir, genre_folders, parse_filename,
                read_duration):
        """
        Seed the index from already-sorted genre folders. Names there are already
        clean ("Artist (ft ...) - Title.ext"), so parse_filename recovers
        artist/title. Returns how many records were added.
        """
        # full reseed: the genre folders are the source of truth
        self.db.execute("DELETE FROM sorted")
        self.db.commit()
        added = 0
        for genre in genre_folders:
            if genre == "Unknown":
                continue
            folder = os.path.join(library_dir, genre)
            if not os.path.isdir(folder):
                continue
            for entry in os.listdir(folder):
                path = os.path.join(folder, entry)
                if not os.path.isfile(path):
                    continue
                parsed = parse_filename(entry)
                akey = make_key(parsed.get("artist"), parsed.get("title"),
                                parsed.get("extended"))
                duration = read_duration(path)
                self.add(akey, duration, parsed.get("artist"),
                         parsed.get("title"), genre, entry)
                added += 1
        return added
