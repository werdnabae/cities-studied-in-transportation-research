"""Country reference data: ISO-2 <-> name, continent, Global North/South, English.

Built on GeoNames countryInfo.txt (downloaded once). Provides reconciliation from
Scopus affiliation-country name strings to ISO-2 so author geography can be compared
to study geography on a common key.

Run standalone to self-test:  python3 -m src.countries
"""
from __future__ import annotations
import urllib.request
from . import config

RAW = config.EXTERNAL / "countryInfo.txt"
URL = "https://download.geonames.org/export/dump/countryInfo.txt"

CONTINENT = {"AF": "Africa", "AS": "Asia", "EU": "Europe", "NA": "North America",
             "SA": "South America", "OC": "Oceania", "AN": "Antarctica"}

# Global North operationalization (UN/Brandt-line style): high-income economies.
# Europe + Northern America + a small set of high-income Asia/Oceania economies.
GLOBAL_NORTH_EXTRA = {"JP", "KR", "IL", "AU", "NZ", "SG", "HK", "TW", "MO", "BN",
                      "AE", "QA", "KW", "BH", "SA", "OM", "US", "CA"}
# Countries where English is an official / primary working language (study/author).
ENGLISH = {"US", "GB", "CA", "AU", "NZ", "IE", "ZA", "IN", "PK", "NG", "GH", "KE",
           "UG", "TZ", "ZW", "ZM", "MW", "SG", "PH", "MY", "JM", "TT", "BB", "BS",
           "BZ", "GY", "FJ", "PG", "MT", "HK"}

# Scopus / common name variants -> ISO-2 (only those that differ from GeoNames name)
ALIASES = {
    "russian federation": "RU", "viet nam": "VN", "vietnam": "VN",
    "south korea": "KR", "republic of korea": "KR", "korea": "KR",
    "north korea": "KP", "iran": "IR", "syrian arab republic": "SY",
    "syria": "SY", "tanzania": "TZ", "united republic of tanzania": "TZ",
    "bolivia": "BO", "venezuela": "VE", "laos": "LA", "moldova": "MD",
    "czech republic": "CZ", "czechia": "CZ", "macedonia": "MK",
    "north macedonia": "MK", "ivory coast": "CI", "cote d'ivoire": "CI",
    "brunei darussalam": "BN", "brunei": "BN", "hong kong": "HK",
    "macao": "MO", "macau": "MO", "taiwan": "TW", "palestine": "PS",
    "state of palestine": "PS", "congo": "CG",
    "democratic republic congo": "CD", "the netherlands": "NL",
    "netherlands": "NL", "usa": "US", "united states": "US",
    "uk": "GB", "united kingdom": "GB", "swaziland": "SZ", "eswatini": "SZ",
}

_ISO2 = None      # iso2 -> {name, continent, iso3, pop}
_NAME2ISO = None  # lowercased name -> iso2

def _ensure():
    global _ISO2, _NAME2ISO
    if _ISO2 is not None:
        return
    if not RAW.exists():
        RAW.write_bytes(urllib.request.urlopen(URL, timeout=120).read())
    _ISO2, _NAME2ISO = {}, {}
    for line in RAW.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split("\t")
        if len(p) < 9:
            continue
        iso2, iso3, name, continent = p[0], p[1], p[4], p[8]
        try:
            pop = int(p[7] or 0)
        except ValueError:
            pop = 0
        _ISO2[iso2] = {"name": name, "continent": continent, "iso3": iso3, "pop": pop}
        _NAME2ISO[name.lower()] = iso2
    _NAME2ISO.update(ALIASES)

def to_iso2(name_or_code):
    _ensure()
    if not name_or_code:
        return None
    s = str(name_or_code).strip()
    if len(s) == 2 and s.upper() in _ISO2:
        return s.upper()
    return _NAME2ISO.get(s.lower())

def continent(iso2):
    _ensure()
    return CONTINENT.get(_ISO2.get(iso2, {}).get("continent"), None)

def name(iso2):
    _ensure()
    return _ISO2.get(iso2, {}).get("name")

def is_global_north(iso2):
    _ensure()
    if iso2 in GLOBAL_NORTH_EXTRA:
        return True
    return _ISO2.get(iso2, {}).get("continent") in {"EU", "NA"} and iso2 not in {
        "MX", "GT", "HN", "NI", "SV", "CU", "HT", "DO", "JM", "BZ"}  # NA non-high-income

def is_english(iso2):
    return iso2 in ENGLISH

def all_countries():
    """Yield (iso2, continent_name, population) for every country."""
    _ensure()
    for iso2, d in _ISO2.items():
        yield iso2, CONTINENT.get(d["continent"]), d["pop"]

def iso3_to_iso2(iso3):
    _ensure()
    for i2, d in _ISO2.items():
        if d.get("iso3") == iso3:
            return i2
    return None

def continent_population():
    """Continent name -> total population (and 'World')."""
    out = {}
    world = 0
    for _, cont, pop in all_countries():
        if cont:
            out[cont] = out.get(cont, 0) + pop
            world += pop
    out["World"] = world
    return out

def main():
    _ensure()
    print(f"Loaded {len(_ISO2)} countries.")
    for t in ["United States", "United Kingdom", "Russian Federation", "South Korea",
              "China", "Nigeria", "Brazil", "Viet Nam", "Hong Kong", "Iran"]:
        i = to_iso2(t)
        print(f"  {t:20} -> {i}  {continent(i)}  north={is_global_north(i)} eng={is_english(i)}")

if __name__ == "__main__":
    main()
