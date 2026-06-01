"""Part D: full-text recall sensitivity (no annotation, uses ScienceDirect access).

Re-extracts study cities from FULL TEXT for a random sample and compares to the
metadata-based extractor, to show (i) the metadata extractor's primary city agrees
with full text, (ii) how many place-based papers metadata misses, and (iii) that the
city distribution and Gini are stable. Run:  python3 -m src.fulltext_check [N]
"""
from __future__ import annotations
import sys, json
from collections import Counter
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from . import config
from .elsevier_client import get, QuotaExhausted
from .extract import clean_text, find_cities, BENCHMARK_PSEUDO_CITIES

N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
SEED = 7

def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    if n == 0 or x.sum() == 0: return float("nan")
    return (2*np.sum((np.arange(1, n+1))*x)/(n*x.sum())) - (n+1)/n

def fulltext_primary(text):
    score = Counter()
    for c, ctry, _ in find_cities(clean_text(text)):
        if (c, ctry) not in BENCHMARK_PSEUDO_CITIES:
            score[(c, ctry)] += 1
    if not score:
        return None
    return score.most_common(1)[0][0]

def fetch_fulltext(doi):
    try:
        r = get(config.ARTICLE_RETRIEVAL + doi, "article_retrieval",
                params={"view": "FULL"}, accept="application/json")
        j = r.json().get("full-text-retrieval-response", {})
        txt = j.get("originalText")
        if isinstance(txt, str) and len(txt) > 500:
            return txt
    except QuotaExhausted:
        raise
    except Exception:
        return None
    return None

def main():
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    arts = arts.dropna(subset=["doi"])
    sample = arts.sample(n=min(N, len(arts)), random_state=SEED).reset_index(drop=True)

    rows, n_ok = [], 0
    for _, a in sample.iterrows():
        txt = fetch_fulltext(a["doi"])
        if not txt:
            continue
        n_ok += 1
        ftp = fulltext_primary(txt)
        meta = (a["study_city"], a["study_country"]) if pd.notna(a["study_city"]) else None
        rows.append({"eid": a["eid"], "meta": meta, "ft": ftp,
                     "meta_city_in_ft": (meta is not None and meta == ftp) or
                                        (meta is not None and ftp is not None and meta[0] == ftp[0])})
    df = pd.DataFrame(rows)
    R = json.loads((config.PROCESSED / "results.json").read_text())

    placed_meta = df[df["meta"].notna()]
    none_meta = df[df["meta"].isna()]
    agree = placed_meta.apply(lambda r: r["meta"] == r["ft"], axis=1).mean() if len(placed_meta) else float("nan")
    recall_gap = none_meta["ft"].notna().mean() if len(none_meta) else float("nan")

    # distribution stability on full text vs metadata, same sample
    ft_counts = df["ft"].dropna().value_counts()
    meta_counts = df["meta"].dropna().value_counts()
    overlap = len(set(ft_counts.head(20).index) & set(meta_counts.head(20).index))

    R["fulltext"] = {
        "n_sampled": int(len(sample)), "n_retrieved": int(n_ok),
        "primary_agreement": round(float(agree), 3),
        "recall_gap_metadata_none_placed_by_fulltext": round(float(recall_gap), 3),
        "gini_metadata_sample": round(float(gini(meta_counts.values)), 3),
        "gini_fulltext_sample": round(float(gini(ft_counts.values)), 3),
        "top20_overlap": int(overlap)}
    (config.PROCESSED / "results.json").write_text(json.dumps(R, indent=2, default=str))
    print(json.dumps(R["fulltext"], indent=2))

if __name__ == "__main__":
    main()
