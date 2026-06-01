"""Draw a reproducible random sample for BLIND manual validation of the study-city
extractor. Annotator sees only title+abstract (not the prediction), records the
true primary study city, then score_validation.py joins back to predictions.

Outputs:
  data/processed/validation_blind.csv   eid,journal,year,title,abstract + blank
                                         true_city,true_country,has_city,notes
  data/processed/validation_pred.parquet  eid,pred_city,pred_country (hidden key)

Run:  python3 -m src.sample_for_labeling [N]
"""
from __future__ import annotations
import sys, json
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
from . import config
from .extract import clean_text

N = int(sys.argv[1]) if len(sys.argv) > 1 else 150
SEED = 42

def main():
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    sample = arts.sample(n=min(N, len(arts)), random_state=SEED).reset_index(drop=True)

    # rebuild title/abstract text from raw jsonl (articles.parquet doesn't store it)
    text_by_eid = {}
    want = set(sample["eid"])
    for fp in config.RAW_SCOPUS.glob("*.jsonl"):
        with open(fp) as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("eid") in want:
                    text_by_eid[rec["eid"]] = (
                        clean_text(rec.get("dc:title")),
                        clean_text(rec.get("dc:description")))

    blind = pd.DataFrame({
        "eid": sample["eid"],
        "journal": sample["journal"],
        "year": sample["year"],
        "title": [text_by_eid.get(e, ("", ""))[0] for e in sample["eid"]],
        "abstract": [text_by_eid.get(e, ("", ""))[1] for e in sample["eid"]],
        "has_city": "",        # annotator: 1 if the paper has a specific primary study city, else 0
        "true_city": "",       # annotator: city name (GeoNames-style) or blank
        "true_country": "",    # annotator: ISO-2 country or blank
        "notes": "",
    })
    pred = sample[["eid", "study_city", "study_country"]].rename(
        columns={"study_city": "pred_city", "study_country": "pred_country"})

    blind.to_csv(config.PROCESSED / "validation_blind.csv", index=False)
    pred.to_parquet(config.PROCESSED / "validation_pred.parquet")
    print(f"Wrote {len(blind)} rows to validation_blind.csv (blind) and predictions key.")
    print(f"Predicted a city for {sample['study_city'].notna().sum()}/{len(sample)} sampled.")

if __name__ == "__main__":
    main()
