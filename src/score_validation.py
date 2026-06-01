"""Score the extractor against blind manual labels.

Reads validation_labeled.csv (the blind file with true_city/true_country/has_city
filled in) and validation_pred.parquet, then reports:
  * Detection  : binary "has a study city?" precision/recall/F1
  * City-level : of predicted cities, share matching the true city
  * Country-lvl: same at country granularity (more forgiving of disambiguation)

Run:  python3 -m src.score_validation [labeled_csv]
"""
from __future__ import annotations
import sys
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
from unidecode import unidecode

from . import config


def norm(s):
    if pd.isna(s) or str(s).strip() == "":
        return ""
    return unidecode(str(s)).strip().lower()

def main():
    labeled_path = sys.argv[1] if len(sys.argv) > 1 else str(config.PROCESSED / "validation_labeled.csv")
    lab = pd.read_csv(labeled_path)
    pred = pd.read_parquet(config.PROCESSED / "validation_pred.parquet")
    df = lab.merge(pred, on="eid", how="left")
    try:
        blind = pd.read_csv(config.PROCESSED / "validation_blind.csv")[["eid", "title"]]
        df = df.merge(blind, on="eid", how="left")
    except Exception:
        df["title"] = ""

    df["true_has"] = df["has_city"].apply(lambda x: str(x).strip() in {"1", "1.0", "yes", "true"})
    df["pred_has"] = df["pred_city"].notna() & (df["pred_city"].astype(str).str.strip() != "")

    tp = (df.true_has & df.pred_has).sum()
    fp = (~df.true_has & df.pred_has).sum()
    fn = (df.true_has & ~df.pred_has).sum()
    tn = (~df.true_has & ~df.pred_has).sum()
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")

    print(f"N labeled = {len(df)}")
    print("\n== Detection (has a study city?) ==")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  precision={prec:.3f} recall={rec:.3f} F1={f1:.3f}")

    both = df[df.true_has & df.pred_has].copy()
    both["city_ok"] = both.apply(lambda r: norm(r.true_city) == norm(r.pred_city), axis=1)
    both["ctry_ok"] = both.apply(lambda r: norm(r.true_country) == norm(r.pred_country), axis=1)
    print("\n== Given both predicted & true have a city ==")
    print(f"  city-level accuracy   = {both.city_ok.mean():.3f}  (n={len(both)})")
    print(f"  country-level accuracy= {both.ctry_ok.mean():.3f}")

    # end-to-end correct = predicted exactly right city among all true-positives
    e2e_city = (both.city_ok.sum()) / (df.true_has.sum()) if df.true_has.sum() else float("nan")
    print(f"\n  end-to-end city recall (correct city / all true cities) = {e2e_city:.3f}")

    print("\nDisagreements (true vs pred):")
    for _, r in df[df.true_has != df.pred_has].head(20).iterrows():
        print(f"  true_has={int(r.true_has)} pred={r.pred_city!s:18} | {str(r.title)[:70]}")
    for _, r in both[~both.city_ok].head(20).iterrows():
        print(f"  MISMATCH true={r.true_city!s:16} pred={r.pred_city!s:16} | {str(r.title)[:60]}")

if __name__ == "__main__":
    main()
