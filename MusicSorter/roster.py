"""
roster.py
=========
Per-folder "living" artist lists. Each managed genre folder holds an
`_artists.txt` listing the artists expected there. A roster match is the
strongest placement signal we have (artist identity beats a generic tag), so
once e.g. Nameless is in the Genge roster, every Nameless song goes to Genge.

File format (DJ-editable):
    # comment / header
    Jua Cali
    Nonini
    # --- auto-added by updater (prune freely; lines above are kept) ---
    Kleptomaniax

The updater only rewrites lines BELOW the marker; the manual section is never
touched. Matching is on lookup._norm (case/space-insensitive).
"""

import os
import genre_rules
from lookup import _norm

ROSTER_FILE = "_artists.txt"
AUTO_MARKER = "# --- auto-added by updater (prune freely; lines above are kept) ---"
HEADER = "# Artists expected in this folder. One artist per line. Edit freely."

# Era folders -> (base scene, the Old/New pair) so the roster decides the SCENE
# while the release year still decides the ERA.
ERA_FOLDERS = {
    "Old School Bongo": "Bongo", "New School Bongo": "Bongo",
    "Old School Rhumba": "Rhumba", "New School Rhumba": "Rhumba",
}

# Managed scenes: online-seeded + gated. Globals (Hip Hop, RnB, Pop, EDM, House,
# Trap, Gospel) are not seeded here but still honoured if a roster file exists.
# Each entry: last.fm tags to chart, and a starter artist list.
SEED = {
    "Kenyan Old School - Genge": {
        "tags": ["genge"],
        "seeds": ["Jua Cali", "Nonini", "Nameless", "P-Unit", "Mejja",
                  "Prezzo", "Kleptomaniax", "E-Sir", "Redsan", "Collo",
                  "Abbas Kubaff", "Kleptomaniax", "Mr Lenny", "Circuite & Joel"],
    },
    "Kenyan New School": {
        "tags": ["gengetone", "kenyan drill", "kenyan hip hop"],
        "seeds": ["Ethic", "Sailors", "Wakadinali", "Buruklyn Boyz",
                  "Femi One", "Ssaru", "Trio Mio", "Boondocks Gang",
                  "Mbogi Genje", "Mejja", "Exray Taniua", "Wakavinye"],
    },
    "Kenyan RnB": {
        "tags": ["kenyan r&b"],
        "seeds": ["Sauti Sol", "Bensoul", "Nviiri the Storyteller",
                  "Otile Brown", "Nyashinski", "Xenia Manasseh", "Bien"],
    },
    "Old School Bongo": {
        "tags": ["bongo flava"],
        "seeds": ["Professor Jay", "Juma Nature", "Ferooz", "AY", "Mr Nice",
                  "Lady Jaydee", "Dully Sykes", "TID", "Q Chief", "Ray C"],
    },
    "New School Bongo": {
        "tags": ["bongo flava"],
        "seeds": ["Diamond Platnumz", "Harmonize", "Rayvanny", "Zuchu",
                  "Mbosso", "Alikiba", "Marioo", "Jux", "Nandy", "Lava Lava"],
    },
    "Old School Rhumba": {
        "tags": ["rumba", "soukous"],
        "seeds": ["Franco", "Tabu Ley Rochereau", "Madilu System",
                  "Pepe Kalle", "Sam Mangwana", "TPOK Jazz"],
    },
    "New School Rhumba": {
        "tags": ["rumba", "soukous", "ndombolo"],
        "seeds": ["Koffi Olomide", "Fally Ipupa", "Ferre Gola",
                  "Werrason", "Extra Musica", "Awilo Longomba"],
    },
    "Dancehall": {
        "tags": ["dancehall"],
        "seeds": ["Vybz Kartel", "Mavado", "Popcaan", "Aidonia", "Alkaline",
                  "Konshens", "Spice", "Shenseea", "Masicka"],
    },
    "Ragga": {
        "tags": ["ragga", "raggamuffin"],
        "seeds": ["Shabba Ranks", "Super Cat", "Capleton", "Sizzla",
                  "Elephant Man", "Beenie Man"],
    },
    "Reggae": {
        "tags": ["reggae"],
        "seeds": ["Bob Marley", "Gregory Isaacs", "Dennis Brown",
                  "Chronixx", "Jah Cure", "Morgan Heritage"],
    },
    "Roots": {
        "tags": ["roots reggae"],
        "seeds": ["Burning Spear", "Culture", "The Abyssinians",
                  "Protoje", "Israel Vibration"],
    },
    "Lovers Rock Riddims": {
        "tags": ["lovers rock"],
        "seeds": ["Beres Hammond", "Sanchez", "Maxi Priest", "Freddie McGregor"],
    },
    "Soca": {
        "tags": ["soca"],
        "seeds": ["Machel Montano", "Bunji Garlin", "Kes", "Destra Garcia",
                  "Patrice Roberts"],
    },
    "Amapiano": {
        "tags": ["amapiano"],
        "seeds": ["Kabza De Small", "DJ Maphorisa", "Focalistic", "Tyler ICU",
                  "Daliwonga", "Young Stunna"],
    },
    "Afrobeats": {
        "tags": ["afrobeats"],
        "seeds": ["Burna Boy", "Wizkid", "Davido", "Rema", "Asake", "Ayra Starr",
                  "Omah Lay", "Tems", "Fireboy DML"],
    },
    "Zouk": {
        "tags": ["zouk"],
        "seeds": ["Kassav", "Jocelyne Beroard", "Edith Lefel"],
    },
}

MANAGED = list(SEED.keys())


def _split_sections(lines):
    """Return (manual_lines, auto_lines) around the AUTO_MARKER."""
    if AUTO_MARKER in lines:
        i = lines.index(AUTO_MARKER)
        return lines[:i], lines[i + 1:]
    return lines, []


def _names_from(lines):
    out = []
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


class RosterStore:
    def __init__(self, library_dir):
        self.library_dir = library_dir
        self.manual = {}   # norm name -> set(folder)  (curated, trusted)
        self.auto = {}     # norm name -> set(folder)  (machine-added, noisier)

    def path(self, folder):
        return os.path.join(self.library_dir, folder, ROSTER_FILE)

    def load(self, genre_folders):
        self.manual, self.auto = {}, {}
        for folder in genre_folders:
            p = self.path(folder)
            if not os.path.isfile(p):
                continue
            with open(p, encoding="utf-8") as f:
                man_lines, auto_lines = _split_sections(f.read().splitlines())
            for name in _names_from(man_lines):
                self.manual.setdefault(_norm(name), set()).add(folder)
            for name in _names_from(auto_lines):
                self.auto.setdefault(_norm(name), set()).add(folder)
        return self

    def _match(self, table, artist, year):
        folders = table.get(_norm(artist))
        if not folders:
            return None
        # collapse era pairs to one scene so we don't get a false ambiguity
        scenes = {ERA_FOLDERS.get(f, f) for f in folders}
        if len(scenes) != 1:
            return None                      # genuinely ambiguous
        scene = scenes.pop()
        if scene in ("Bongo", "Rhumba"):
            return genre_rules.resolve_era(scene, year)
        return next(iter(folders)) if len(folders) == 1 else scene

    def folder_for_artist(self, artist, year):
        """Exact roster match -> (folder, source); 'manual' is trusted, 'auto'
        is a weaker suggestion. Era decided by year."""
        if not artist:
            return None
        m = self._match(self.manual, artist, year)
        if m:
            return (m, "manual")
        a = self._match(self.auto, artist, year)
        if a:
            return (a, "auto")
        return None

    # ----- writing (seed / update) -----
    def read_file(self, folder):
        p = self.path(folder)
        if not os.path.isfile(p):
            return [], []
        with open(p, encoding="utf-8") as f:
            return _split_sections(f.read().splitlines())

    def write_manual_and_auto(self, folder, manual_lines, auto_names):
        os.makedirs(os.path.join(self.library_dir, folder), exist_ok=True)
        manual_names = set(_norm(n) for n in _names_from(manual_lines))
        # keep only auto names not already in the manual section, de-duped
        seen, clean_auto = set(), []
        for n in auto_names:
            k = _norm(n)
            if k and k not in manual_names and k not in seen:
                seen.add(k)
                clean_auto.append(n)
        body = manual_lines[:] if manual_lines else [HEADER]
        body += ["", AUTO_MARKER] + sorted(clean_auto, key=str.lower)
        with open(self.path(folder), "w", encoding="utf-8") as f:
            f.write("\n".join(body).rstrip() + "\n")

    def seed_folder(self, folder, seed_names):
        """Create file if missing; put starter names in the MANUAL section once."""
        manual, auto = self.read_file(folder)
        if not manual:
            manual = [HEADER] + list(seed_names)
        self.write_manual_and_auto(folder, manual, _names_from(auto))

    def add_auto(self, folder, new_names):
        manual, auto = self.read_file(folder)
        self.write_manual_and_auto(folder, manual, _names_from(auto) + list(new_names))
