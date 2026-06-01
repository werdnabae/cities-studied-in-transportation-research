"""Day-one sanity check: validate ISSNs, report corpus sizes, test full-text.

Run from project root:  python3 -m src.validate
"""
import json

from . import config
from .elsevier_client import get


def issn_count(issn):
    r = get(config.SCOPUS_SEARCH, "scopus_search",
            params={"query": f"ISSN({issn})", "count": 1})
    j = r.json()["search-results"]
    total = int(j["opensearch:totalResults"])
    # grab one DOI to test full text
    doi = None
    if j.get("entry") and "prism:doi" in j["entry"][0]:
        doi = j["entry"][0]["prism:doi"]
    return total, doi, r.headers.get("X-RateLimit-Remaining")

def test_fulltext(doi):
    try:
        r = get(config.ARTICLE_RETRIEVAL + doi, "article_retrieval",
                params={"view": "FULL"}, accept="application/json")
        j = r.json()
        # presence of originalText/body indicates entitlement
        body = json.dumps(j)
        has_text = ("originalText" in body) or ("ce:para" in body) or len(body) > 8000
        return r.status_code, has_text, len(body)
    except Exception as e:
        return f"ERR {e}", False, 0

def main():
    print(f"API key loaded: {bool(config.API_KEY)} | Insttoken: {bool(config.INST_TOKEN)}\n")
    grand_total = 0
    first_doi = None
    print(f"{'ISSN':<11} {'N articles':>10}  journal")
    print("-" * 70)
    for title, issn, tier in config.JOURNALS:
        try:
            total, doi, remaining = issn_count(issn)
            grand_total += total
            if first_doi is None and doi:
                first_doi = doi
            flag = "" if total > 0 else "  <-- ZERO, check ISSN"
            print(f"{issn:<11} {total:>10,}  {title[:42]}{flag}")
        except Exception as e:
            print(f"{issn:<11} {'ERR':>10}  {title[:42]} :: {e}")
    print("-" * 70)
    print(f"{'TOTAL':<11} {grand_total:>10,}  articles across {len(config.JOURNALS)} journals\n")

    if first_doi:
        print(f"Full-text entitlement test on DOI {first_doi} ...")
        status, has_text, size = test_fulltext(first_doi)
        print(f"  status={status}  has_full_text={has_text}  payload_bytes={size}")

if __name__ == "__main__":
    main()
