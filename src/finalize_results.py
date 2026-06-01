"""Augment results.json with (a) validation metrics and (b) a precision-robustness
check: recompute concentration on the high-precision title/keyword-anchored subset
to show the headline findings are stable. Run AFTER analysis + scoring.

Run:  python3 -m src.finalize_results
"""
from __future__ import annotations
import json
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from . import config
from .analysis import gini

def main():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    placed = arts.dropna(subset=["study_city"])

    # high-precision subset: primary city came from title or keywords (not abstract-only)
    anchored = placed[placed["study_src"].isin(["title", "keywords"])]
    c_all = placed.groupby(["study_city", "study_country"]).size()
    c_anc = anchored.groupby(["study_city", "study_country"]).size()
    R["robustness"] = {
        "anchored_n": int(len(anchored)),
        "anchored_share_of_placed": round(100 * len(anchored) / len(placed), 1),
        "gini_all": round(float(gini(c_all.values)), 3),
        "gini_anchored": round(float(gini(c_anc.values)), 3),
        "top20_share_all": round(100 * c_all.sort_values(ascending=False).head(20).sum() / c_all.sum(), 1),
        "top20_share_anchored": round(100 * c_anc.sort_values(ascending=False).head(20).sum() / c_anc.sum(), 1),
        "top20_overlap": int(len(set(c_all.sort_values(ascending=False).head(20).index)
                                 & set(c_anc.sort_values(ascending=False).head(20).index))),
    }

    # validation metrics (recompute from labeled file so the paper cites live numbers)
    from unidecode import unidecode
    lab = pd.read_csv(config.PROCESSED / "validation_labeled.csv")
    pred = pd.read_parquet(config.PROCESSED / "validation_pred.parquet")
    d = lab.merge(pred, on="eid", how="left")
    th = d["has_city"].astype(str).str.strip().isin(["1", "1.0"])
    ph = d["pred_city"].notna() & (d["pred_city"].astype(str).str.strip() != "")
    tp = int((th & ph).sum()); fp = int((~th & ph).sum())
    fn = int((th & ~ph).sum()); tn = int((~th & ~ph).sum())
    prec = tp / (tp + fp); rec = tp / (tp + fn)
    both = d[th & ph].copy()
    norm = lambda s: unidecode(str(s)).strip().lower() if pd.notna(s) else ""
    city_ok = both.apply(lambda r: norm(r.true_city) == norm(r.pred_city), axis=1).mean()
    R["validation"] = {
        "n": int(len(d)), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(prec, 3), "recall": round(rec, 3),
        "f1": round(2 * prec * rec / (prec + rec), 3),
        "city_accuracy_given_detection": round(float(city_ok), 3),
        "n_annotators": 3, "method": "independent blind LLM annotation",
    }
    (config.PROCESSED / "results.json").write_text(json.dumps(R, indent=2, default=str))
    print("Validation:", R["validation"])
    print("Robustness:", R["robustness"])

if __name__ == "__main__":
    main()
