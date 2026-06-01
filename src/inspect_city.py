"""Diagnostic: show the article titles where a given city is the PRIMARY study
city, plus the matching source field. Reveals whether a hit is real or a false
friend. Usage:  python3 -m src.inspect_city "Parkersburg" [n]
"""
from __future__ import annotations
import sys, json, warnings
warnings.filterwarnings("ignore")
from . import config
from .extract import process_article, clean_text, find_cities

def main():
    target = sys.argv[1].lower()
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    shown = 0
    for fp in sorted(config.RAW_SCOPUS.glob("*.jsonl")):
        with open(fp) as fh:
            for line in fh:
                rec = json.loads(line)
                a, _ = process_article(rec, fp.stem, fp.stem)
                if a["study_city"] and a["study_city"].lower() == target:
                    title = clean_text(rec.get("dc:title"))
                    # which surface token triggered it
                    src = a["study_src"]
                    field = {"title": title, "keywords": clean_text(rec.get("authkeywords")),
                             "abstract": clean_text(rec.get("dc:description"))}[src]
                    print(f"[{src}] {title[:110]}")
                    shown += 1
                    if shown >= limit:
                        return
    if shown == 0:
        print("no primary matches found")

if __name__ == "__main__":
    main()
