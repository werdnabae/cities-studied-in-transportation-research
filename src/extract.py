"""Extract study cities (title/abstract/keywords) and author cities (affiliations).

Correctness measures (the "no mistakes" pass):
  * Unicode -> ASCII normalization (unidecode) so "São Paulo", "Bogotá",
    "Zürich", "Montréal" match their ASCII gazetteer keys.
  * Strip trailing copyright/publisher boilerplate from abstracts so publisher
    cities never leak in as study locations.
  * Longest-n-gram-wins matching (3 -> 2 -> 1), consumed spans not reused.
  * Deterministic primary-city selection: (weight desc, population desc, name asc).
  * Author cities resolved through the SAME gazetteer (ASCII+lower, "X City"
    fallback) for consistent city identity in the author-vs-study comparison.

Outputs (data/processed/):
  articles.parquet   one row/article
  mentions.parquet   long: one row per (article, studied city)

Run:  python3 -m src.extract
"""
from __future__ import annotations
import json
import re
import html
from collections import Counter
from unidecode import unidecode
import pandas as pd
from . import config

GAZ = json.loads((config.PROCESSED / "gazetteer.json").read_text())
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\.\-']+")
MAXGRAM = 3
# Documented exclusion: in the transport literature "Sioux Falls" is overwhelmingly
# the standard test NETWORK (verified by sampling: every primary hit was a traffic-
# assignment/methods paper), not a study of the actual city. Excluded from study
# locations. Reported as a sensitivity note in the methods.
BENCHMARK_PSEUDO_CITIES = {("Sioux Falls", "US")}
# Trailing boilerplate: "© 2019 Elsevier Ltd. All rights reserved." etc.
COPYRIGHT_RE = re.compile(r"(©|\bcopyright\b|\bcrown copyright\b|\(c\)\s*\d{4}).*$",
                          re.IGNORECASE | re.DOTALL)

def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = COPYRIGHT_RE.sub(" ", s)        # drop publisher/copyright tail
    s = s.replace("|", " ")             # author-keyword separator
    return unidecode(s)                 # accents -> ASCII to match gazetteer keys

def find_cities(text: str):
    """Return [(city, country, pop)] found; longest n-gram wins, spans consumed."""
    toks = TOKEN_RE.findall(text)
    low = [t.lower().strip(".") for t in toks]
    n = len(low)
    used = [False] * n
    found = []
    for size in range(MAXGRAM, 0, -1):
        for i in range(0, n - size + 1):
            if any(used[i:i + size]):
                continue
            key = " ".join(low[i:i + size])
            cand = GAZ.get(key)
            if cand:
                found.append((cand["city"], cand["country"], cand["pop"]))
                for j in range(i, i + size):
                    used[j] = True
    return found

def resolve_author_city(raw_city: str):
    """Map a Scopus affiliation-city string to a canonical gazetteer city."""
    if not raw_city:
        return None
    key = unidecode(raw_city).lower().strip()
    cand = GAZ.get(key)
    if not cand and key.endswith(" city"):          # "Singapore City" -> "singapore"
        cand = GAZ.get(key[:-5].strip())
    if cand:
        return (cand["city"], cand["country"])
    return None

def author_geo(affiliations):
    raw_cities, countries, resolved = [], [], []
    for a in affiliations or []:
        if a.get("city"):
            raw_cities.append(a["city"])
            r = resolve_author_city(a["city"])
            if r:
                resolved.append(r)
        if a.get("country"):
            countries.append(a["country"])
    return raw_cities, sorted(set(countries)), resolved

def process_article(rec, issn, journal):
    title = clean_text(rec.get("dc:title"))
    abstract = clean_text(rec.get("dc:description"))
    keywords = clean_text(rec.get("authkeywords"))
    cover = rec.get("prism:coverDate") or ""
    year = int(cover[:4]) if cover[:4].isdigit() else None

    score = Counter()
    pop_of = {}
    src_of = {}
    for label, hits, w in (("title", find_cities(title), 3),
                           ("keywords", find_cities(keywords), 2),
                           ("abstract", find_cities(abstract), 1)):
        for c, ctry, pop in hits:
            key = (c, ctry)
            if key in BENCHMARK_PSEUDO_CITIES:
                continue
            score[key] += w
            pop_of[key] = pop
            src_of.setdefault(key, label)     # first (highest-weight) source wins

    primary_city = primary_country = primary_src = None
    if score:
        # deterministic: weight desc, population desc, name asc
        best = sorted(score.items(),
                      key=lambda kv: (-kv[1], -pop_of[kv[0]], kv[0][0]))[0][0]
        primary_city, primary_country = best
        primary_src = src_of[best]

    raw_acities, acountries, resolved_a = author_geo(rec.get("affiliation"))
    author_cities = sorted({c for c, _ in resolved_a})
    author_city_countries = sorted({ctry for _, ctry in resolved_a})

    article_row = {
        "eid": rec.get("eid"), "doi": rec.get("prism:doi"), "issn": issn,
        "journal": journal, "year": year,
        "study_city": primary_city, "study_country": primary_country,
        "study_src": primary_src, "n_study_cities": len(score),
        "has_study_city": bool(score),
        "author_cities": author_cities,
        "author_city_countries": author_city_countries,
        "author_countries_raw": acountries,
        "n_aff": len(raw_acities),
        "citedby": rec.get("citedby-count"),
    }
    mention_rows = [
        {"eid": rec.get("eid"), "issn": issn, "year": year, "city": c,
         "country": ctry, "weight": w, "source": src_of[(c, ctry)],
         "pop": pop_of[(c, ctry)]}
        for (c, ctry), w in score.items()
    ]
    return article_row, mention_rows

def main():
    journals = {issn: title for title, issn, _ in config.JOURNALS}
    art_rows, men_rows = [], []
    files = sorted(config.RAW_SCOPUS.glob("*.jsonl"))
    print(f"Processing {len(files)} journal files ...")
    for fp in files:
        issn = fp.stem
        journal = journals.get(issn, issn)
        nrec = 0
        with open(fp) as fh:
            for line in fh:
                rec = json.loads(line)
                a, m = process_article(rec, issn, journal)
                art_rows.append(a); men_rows.extend(m)
                nrec += 1
        print(f"  {issn} {journal[:36]:36} {nrec:>6} articles")
    arts = pd.DataFrame(art_rows)
    mens = pd.DataFrame(men_rows)
    arts.to_parquet(config.PROCESSED / "articles.parquet")
    mens.to_parquet(config.PROCESSED / "mentions.parquet")

    print(f"\nArticles: {len(arts):,} | with >=1 study city: {arts.has_study_city.mean():.1%}")
    print(f"Distinct study cities: {mens['city'].nunique():,} | mentions: {len(mens):,}")
    print("\nStudy-city rate by journal (Part B methodological should be LOW):")
    by_j = arts.groupby("journal")["has_study_city"].mean().sort_values()
    for j, r in by_j.items():
        print(f"  {r:5.1%}  {j[:50]}")
    print("\nTop 20 study cities (primary):")
    top = (arts.dropna(subset=["study_city"])
              .groupby(["study_city", "study_country"]).size()
              .sort_values(ascending=False).head(20))
    for (c, ctry), n in top.items():
        print(f"  {n:>5}  {c}, {ctry}")

if __name__ == "__main__":
    main()
