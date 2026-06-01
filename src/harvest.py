"""Harvest all article metadata for each journal via Scopus Search (COMPLETE view).

Cursor pagination, one resumable JSONL per ISSN. Re-running skips completed journals.
Run:  python3 -m src.harvest
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from . import config
from .elsevier_client import QuotaExhausted, get

FIELDS = ("dc:title", "dc:description", "authkeywords", "prism:coverDate",
          "prism:doi", "eid", "citedby-count", "prism:publicationName", "affiliation")

def slim(entry: dict) -> dict:
    out = {k: entry.get(k) for k in FIELDS}
    # affiliation -> compact list of {city, country, name}
    affs = entry.get("affiliation") or []
    out["affiliation"] = [
        {"name": a.get("affilname"), "city": a.get("affiliation-city"),
         "country": a.get("affiliation-country")} for a in affs
    ]
    return out

def harvest_issn(issn: str, expected: int | None = None):
    out_path = config.RAW_SCOPUS / f"{issn}.jsonl"
    done_marker = config.RAW_SCOPUS / f"{issn}.done"
    if done_marker.exists():
        print(f"  {issn}: already complete, skipping")
        return
    cursor = "*"
    n = 0
    with open(out_path, "w") as fh:
        while True:
            r = get(config.SCOPUS_SEARCH, "scopus_search", params={
                "query": f"ISSN({issn})", "view": "COMPLETE",
                "count": 25, "cursor": cursor})
            sr = r.json()["search-results"]
            entries = sr.get("entry", [])
            if not entries or (len(entries) == 1 and "error" in entries[0]):
                break
            for e in entries:
                fh.write(json.dumps(slim(e)) + "\n")
            n += len(entries)
            nxt = sr.get("cursor", {}).get("@next")
            sys.stdout.write(f"\r  {issn}: {n} records")
            sys.stdout.flush()
            if not nxt or nxt == cursor:
                break
            cursor = nxt
    done_marker.write_text(str(n))
    print(f"  -> {issn}: {n} records written"
          + (f" (expected ~{expected})" if expected else ""))

def main():
    print(f"Harvesting {len(config.ALL_ISSNS)} journals -> {config.RAW_SCOPUS}")
    for title, issn, tier in config.JOURNALS:
        print(f"[{tier}] {title}")
        try:
            harvest_issn(issn)
        except QuotaExhausted as q:
            print(f"\nQUOTA STOP: {q}\nRe-run later to resume (completed journals skipped).")
            return
    print("\nALL DONE.")

if __name__ == "__main__":
    main()
