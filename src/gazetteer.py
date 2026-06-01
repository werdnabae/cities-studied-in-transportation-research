"""Build a robust city gazetteer from GeoNames cities15000 for geoparsing.

Geoparsing's classic failure mode is common words that are also place names
(hail, mora, nice, mobile, reading, split). We defend in depth:

  1. Alternate names are ingested ONLY if multi-word (e.g. "New York"); raw
     single-token GeoNames alt-names are the main pollution source and are dropped.
  2. Every single-token key is filtered against the system dictionary
     (/usr/share/dict/words, lowercased) AND a manual stoplist.
  3. POPULATION OVERRIDE: a single-token key that is a dictionary word is kept
     only if the city is genuinely large (>= POP_OVERRIDE), so Paris/Lima survive
     while nice/bath/mora/hail are dropped.
  4. Non-dictionary single tokens still require a moderate population floor.
  5. Ambiguous names resolve to the highest-population city.

Produces:
  data/external/cities15000.txt   (raw download)
  data/processed/gazetteer.json   name(lower) -> best candidate
  data/processed/gazetteer_meta.json  build stats for the methods section

Run:  python3 -m src.gazetteer
"""
from __future__ import annotations
import json
import zipfile
import io
import urllib.request
from pathlib import Path
from . import config

URL = "https://download.geonames.org/export/dump/cities15000.zip"
RAW = config.EXTERNAL / "cities15000.txt"
OUT = config.PROCESSED / "gazetteer.json"
META = config.PROCESSED / "gazetteer_meta.json"
DICT_PATH = Path("/usr/share/dict/words")

POP_OVERRIDE = 500_000   # dict-word single-token names kept only if at least this large
POP_FLOOR_SINGLE = 100_000  # non-dict single-token names need at least this
POP_FLOOR_MULTI_DICT = 100_000  # all-dictionary-word phrases ("the point") need this

# Manual stoplist: common words / generic geographic terms that may slip through
# (not necessarily in the dict, or large enough to survive the override).
STOPWORDS = {
    "north", "south", "east", "west", "central", "union", "national", "general",
    "industry", "mission", "summit", "delta", "eden", "hope", "page", "post",
    "model", "survey", "single", "tier", "rural", "urban", "metro", "city",
    "town", "village", "center", "centre", "deal", "bid", "most", "same", "long",
    "best", "white", "green", "house", "garden", "march", "may", "sale", "tours",
}
# Multi-word false friends: method names / common phrases that collide with the
# names of (usually small) places via GeoNames alternate names.
MULTIWORD_STOP = {
    "monte carlo", "monte-carlo", "the gap", "the city", "the dalles",
    "the valley", "the village", "the plains", "the woodlands", "the rock",
    "the entrance", "the hammocks", "the bottom", "the colony", "the crossings",
    "of the", "as is", "no name", "santa claus", "white house",
}

def download():
    if RAW.exists():
        return
    print("Downloading GeoNames cities15000 ...")
    data = urllib.request.urlopen(URL, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        with z.open("cities15000.txt") as f:
            RAW.write_bytes(f.read())
    print(f"  saved {RAW} ({RAW.stat().st_size//1024} KB)")

def load_dictwords() -> set[str]:
    if not DICT_PATH.exists():
        print("WARNING: /usr/share/dict/words missing; dictionary filter disabled")
        return set()
    return {w.strip().lower() for w in DICT_PATH.read_text(errors="ignore").splitlines() if w.strip()}

def accept_key(key: str, pop: int, dictwords: set[str]) -> bool:
    if len(key) < 3 or not all(ord(c) < 128 for c in key):
        return False
    multiword = " " in key
    if multiword:
        if key in MULTIWORD_STOP:
            return False
        toks = key.split()
        if all(t in STOPWORDS for t in toks):
            return False
        # all-dictionary-word phrases ("the point", "the common", "the peak")
        # are generic English and only kept for genuinely large cities.
        if all(t in dictwords for t in toks) and pop < POP_FLOOR_MULTI_DICT:
            return False
        return True
    # single token
    if key in STOPWORDS:
        return False
    is_dictword = key in dictwords
    if is_dictword:
        return pop >= POP_OVERRIDE          # only large cities override the dict
    return pop >= POP_FLOOR_SINGLE          # non-dict still needs moderate size

def build():
    download()
    dictwords = load_dictwords()
    best: dict[str, dict] = {}
    n_rows = 0
    dropped_dict = 0
    for line in RAW.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) < 15:
            continue
        n_rows += 1
        name, ascii_name, alt = p[1], p[2], p[3]
        lat, lon, country = p[4], p[5], p[8]
        try:
            pop = int(p[14] or 0)
        except ValueError:
            pop = 0
        cand = {"city": name, "country": country, "pop": pop,
                "lat": float(lat) if lat else None,
                "lon": float(lon) if lon else None, "geonameid": p[0]}
        # candidate surface names: primary + ascii always; alt names ONLY if multi-word
        names = {name, ascii_name}
        names.update(a for a in alt.split(",") if a and " " in a)
        for nm in names:
            key = nm.strip().lower()
            if not key:
                continue
            if (" " not in key) and (key in dictwords) and pop < POP_OVERRIDE:
                dropped_dict += 1
            if not accept_key(key, pop, dictwords):
                continue
            prev = best.get(key)
            if prev is None or pop > prev["pop"]:
                best[key] = cand
    OUT.write_text(json.dumps(best))
    meta = {"n_cities_rows": n_rows, "n_searchable_names": len(best),
            "pop_override": POP_OVERRIDE, "pop_floor_single": POP_FLOOR_SINGLE,
            "dict_words_loaded": len(dictwords),
            "single_token_dict_drops": dropped_dict}
    META.write_text(json.dumps(meta, indent=2))
    print(f"Parsed {n_rows} cities -> {len(best)} searchable names "
          f"(dropped ~{dropped_dict} single-token dict collisions)")
    print(f"  wrote {OUT}")

    print("\nKEEP checks (should all resolve):")
    for t in ["london", "beijing", "shanghai", "rio de janeiro", "new york",
              "são paulo", "sao paulo", "lagos", "nairobi", "paris", "lima",
              "hong kong", "delhi", "mexico city"]:
        c = best.get(t)
        print(f"  {t:16} -> {c['city']+', '+c['country'] if c else '** MISSING **'}")
    print("\nDROP checks (should all be gone):")
    for t in ["mora", "hail", "kars", "nice", "mobile", "bath", "reading",
              "novato", "carrao", "model", "data", "road", "transit"]:
        c = best.get(t)
        print(f"  {t:16} -> {('STILL PRESENT: '+c['city']+', '+c['country']) if c else 'dropped (good)'}")

if __name__ == "__main__":
    build()
