"""
genre_rules.py
==============
Maps the metadata we gather online (tags + artist region + release year) onto
the DJ's own genre folders, and decides Old School vs New School.

EVERYTHING you might want to tweak lives at the top of this file:
  * GENRE_FOLDERS   - the canonical folder names
  * ERA_CUTOFFS     - the Old/New School pivot years
  * TAG_RULES       - which online tags map to which base genre
  * REGION rules    - inside classify(), how country overrides generic tags

The classifier returns (folder_name, confidence, reason). Confidence is just a
count of how many independent signals agreed; sort_music.py sends anything below
the configured threshold to the _Review folder instead of auto-filing it.
"""

# --- Canonical folders (spelling normalised from your original list) -------
GENRE_FOLDERS = [
    "Trap", "Dancehall", "Reggae", "Roots", "Old School Riddims",
    "Lovers Rock Riddims", "RnB", "House", "New School Rhumba",
    "Old School Rhumba", "Zouk", "Old School Bongo", "New School Bongo",
    "EDM", "Afrobeats", "Amapiano", "3 Step", "Pop",
    "Kenyan Old School - Genge", "Kenyan New School", "Kenyan RnB",
    "Soca", "Ragga",
    # Sensible additions for your library:
    "Hip Hop", "Gospel",
    # Catch-all:
    "Unknown",
]

# --- Old School vs New School pivot years (edit freely) --------------------
# A song from BEFORE the year is "Old School"; the year or later is "New School".
ERA_CUTOFFS = {
    "Rhumba": 2000,   # Franco/Tabu Ley classic soukous vs modern (Fally, Ferre)
    "Bongo":  2012,   # pre-Diamond era vs the Wasafi/modern bongo wave
    "Riddims": 2008,  # golden riddim era vs later
    "Kenyan": 2012,   # Genge era (Jua Cali, Nonini) vs Gengetone/drill/new wave
}

# --- Tag -> base genre. Order matters: most specific first. -----------------
# We test whether any keyword appears as a substring in the combined tag text.
TAG_RULES = [
    (["amapiano"],                                   "Amapiano"),
    (["3-step", "3 step", "three step"],             "3 Step"),
    (["bongo flava", "bongo fleva", "bongo", "singeli", "mdundo"], "Bongo"),
    (["gengetone", "genge"],                         "Genge"),
    (["soukous", "rhumba", "rumba", "lingala", "ndombolo", "congolese"], "Rhumba"),
    (["lovers rock"],                                "Lovers Rock Riddims"),
    (["riddim", "version", "instrumental dub"],      "Old School Riddims"),
    (["roots reggae", "roots"],                      "Roots"),
    (["ragga", "raggamuffin"],                       "Ragga"),
    (["dancehall"],                                  "Dancehall"),
    (["reggae"],                                     "Reggae"),
    (["soca"],                                       "Soca"),
    (["zouk", "kizomba"],                            "Zouk"),
    (["afrobeat", "afro-beat", "afrobeats", "afro pop", "afropop",
      "afro-fusion", "naija", "alte"],               "Afrobeats"),
    (["trap"],                                       "Trap"),
    (["drill"],                                      "Hip Hop"),
    (["gospel", "worship", "praise", "christian"],   "Gospel"),
    (["deep house", "afro house", "amapiano house", "house"], "House"),
    (["dubstep", "techno", "trance", "electro", "edm", "electronic",
      "drum and bass", "dnb"],                       "EDM"),
    # RnB before Hip Hop: many sung-R&B artists also carry a broad "hip hop"
    # tag; an explicit r&b/soul tag should win. Pure rappers lack the rnb tag.
    (["r&b", "rnb", "r and b", "neo soul", "neo-soul", "contemporary r&b",
      "soul"],                                       "RnB"),
    (["hip hop", "hip-hop", "rap", "gangsta", "g-funk", "boom bap",
      "conscious hip hop"],                          "Hip Hop"),
    (["pop"],                                        "Pop"),
]

# Bases that still need an era decision applied:
_ERA_BASES = {"Rhumba", "Bongo", "Kenyan"}
# Direct base -> folder (no era split):
_DIRECT = {
    "Genge": "Kenyan Old School - Genge",   # genge tag alone implies old-school KE
    "KenyanRnB": "Kenyan RnB",
}


def resolve_era(base, year):
    """Turn an era-sensitive base genre into the right Old/New folder."""
    if base == "Rhumba":
        if year and year < ERA_CUTOFFS["Rhumba"]:
            return "Old School Rhumba"
        return "New School Rhumba"
    if base == "Bongo":
        if year and year < ERA_CUTOFFS["Bongo"]:
            return "Old School Bongo"
        return "New School Bongo"
    if base == "Kenyan":
        if year and year < ERA_CUTOFFS["Kenyan"]:
            return "Kenyan Old School - Genge"
        return "Kenyan New School"
    return base


# Country/scene tags -> ISO region, used when MusicBrainz gives no country code.
COUNTRY_TAGS = {
    "kenya": "KE", "kenyan": "KE",
    "tanzania": "TZ", "tanzanian": "TZ", "bongo flava": "TZ", "bongo": "TZ",
    "nigeria": "NG", "nigerian": "NG", "naija": "NG",
    "jamaica": "JM", "jamaican": "JM",
    "congo": "CD", "congolese": "CD", "drc": "CD", "lingala": "CD",
    "uganda": "UG", "ugandan": "UG",
    "south africa": "ZA", "south african": "ZA",
}


def _first_tag_match(tag_text):
    for keys, base in TAG_RULES:
        for k in keys:
            if k in tag_text:
                return base, k
    return None, None


def classify(meta):
    """
    meta keys used:
      tags  : list[str]   (lowercased genre tags from spotify + last.fm + id3)
      region: str|None    (ISO country code of the artist, e.g. 'KE','TZ','JM')
      year  : int|None    (earliest release year)
      spotify_had_genres: bool (reliability signal)
    Returns: (folder, confidence:int, reason:str)
    """
    tags = [t.lower() for t in (meta.get("tags") or [])]
    tag_text = " | ".join(tags)
    region = (meta.get("region") or "").upper()
    year = meta.get("year")

    evidence = []
    if meta.get("spotify_had_genres"):
        evidence.append("spotify")

    base, matched = _first_tag_match(tag_text)
    if matched:
        evidence.append(f"tag:{matched}")

    # If MusicBrainz gave no country code, infer region from a country/scene tag.
    if not region:
        for t in tags:
            if t in COUNTRY_TAGS:
                region = COUNTRY_TAGS[t]
                evidence.append(f"geo:{t}")
                break

    # --- Region overrides: African scenes are routinely mislabelled by global
    #     tag clouds as generic 'pop'/'afrobeats'/'hip hop'. Country wins. ----
    rnb_ish = ("r&b" in tag_text or "rnb" in tag_text or base == "RnB")
    if region == "KE":
        base = "KenyanRnB" if rnb_ish else "Kenyan"
        evidence.append("region:KE")
    elif region == "TZ":
        if base in (None, "Pop", "Afrobeats", "Hip Hop", "RnB"):
            base = "Bongo"
            evidence.append("region:TZ")
    elif region in ("CD", "CG"):  # DR Congo / Congo
        if base in (None, "Pop", "Afrobeats"):
            base = "Rhumba"
            evidence.append("region:CD")
    elif region == "JM":
        if base in (None, "Pop", "Hip Hop"):
            base = "Dancehall"
            evidence.append("region:JM")
    elif region in ("NG", "UG"):   # Nigeria / Uganda -> Afrobeats by default
        if base in (None, "Pop", "RnB", "Hip Hop"):
            base = "Afrobeats"
            evidence.append(f"region:{region}")

    if base is None:
        return ("Unknown", 0, "no tag or region match")

    # supporting evidence: a known release year strengthens the call
    if year:
        evidence.append("year")

    if base in _DIRECT:
        folder = _DIRECT[base]
    elif base in _ERA_BASES:
        folder = resolve_era(base, year)
    else:
        folder = base  # base already equals a folder name

    if folder not in GENRE_FOLDERS:
        folder = "Unknown"

    confidence = len(set(evidence))
    reason = "; ".join(evidence) if evidence else "none"
    return (folder, confidence, reason)
