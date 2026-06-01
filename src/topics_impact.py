"""TRA-strengthening analyses that use only already-harvested data (no annotation):

A. Citation equity: do studies of Global-South / under-represented cities accrue
   fewer citations, controlling for publication year, journal, and city size?
B. Topic x geography: using a transparent author-keyword lexicon, how does the
   geographic skew vary across transport subfields?

Augments results.json and writes tables. Run:  python3 -m src.topics_impact
"""
from __future__ import annotations
import json, re
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from . import config, countries
from .extract import clean_text

GAZ = json.loads((config.PROCESSED / "gazetteer.json").read_text())
CITYPOP = {}
for v in GAZ.values():
    k = (v["city"], v["country"])
    if k not in CITYPOP or v["pop"] > CITYPOP[k]:
        CITYPOP[k] = v["pop"]

# --- transparent subfield lexicon (matched in title+abstract+keywords) ---------
TOPICS = {
    "Safety": r"\b(safety|crash|crashes|collision|accident|injur|fatalit)\w*",
    "Equity & justice": r"\b(equity|justice|inequalit|disadvantage|social exclusion|accessibilit)\w*",
    "Environment & emissions": r"\b(emission|carbon|co2|air quality|pollut|climate|decarboni)\w*",
    "Public transit": r"\b(transit|bus|metro|subway|rail|tram|brt|light rail)\w*",
    "Active travel": r"\b(walk|walking|pedestrian|cycl|bicycle|bike)\w*",
    "Freight & logistics": r"\b(freight|logistic|supply chain|truck|shipping|delivery)\w*",
    "Automation & ITS": r"\b(autonomous|automated|connected vehicle|self-driving|intelligent transport)\w*",
    "Aviation": r"\b(airport|airline|aviation|air transport|flight)\w*",
}

def load_text_by_eid(want):
    out = {}
    for fp in config.RAW_SCOPUS.glob("*.jsonl"):
        with open(fp) as fh:
            for line in fh:
                rec = json.loads(line)
                e = rec.get("eid")
                if e in want:
                    out[e] = clean_text(rec.get("dc:title")) + " " + \
                             clean_text(rec.get("dc:description")) + " " + \
                             clean_text(rec.get("authkeywords"))
    return out

def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    if n == 0 or x.sum() == 0: return float("nan")
    return (2*np.sum((np.arange(1, n+1))*x)/(n*x.sum())) - (n+1)/n

def main():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    placed = arts.dropna(subset=["study_city"]).copy()
    placed["citedby"] = pd.to_numeric(placed["citedby"], errors="coerce").fillna(0)
    placed["pop"] = placed.apply(lambda r: CITYPOP.get((r["study_city"], r["study_country"]), np.nan), axis=1)
    placed["log_pop"] = np.log10(placed["pop"].clip(lower=1))
    placed["north"] = placed["study_country"].map(countries.is_global_north).fillna(False).astype(int)
    placed["english"] = placed["study_country"].map(countries.is_english).astype(int)
    placed["continent"] = placed["study_country"].map(countries.continent).fillna("NA")
    placed = placed.dropna(subset=["year", "pop"])
    placed = placed[(placed.year >= 1995) & (placed.year <= 2024)]

    # ---- A. citation equity -----------------------------------------------
    R["impact_mean_north"] = round(float(placed[placed.north == 1]["citedby"].mean()), 1)
    R["impact_mean_south"] = round(float(placed[placed.north == 0]["citedby"].mean()), 1)
    R["impact_median_north"] = float(placed[placed.north == 1]["citedby"].median())
    R["impact_median_south"] = float(placed[placed.north == 0]["citedby"].median())
    try:
        import statsmodels.formula.api as smf
        import statsmodels.api as sm
        m = smf.glm("citedby ~ north + english + log_pop + C(continent) + C(year) + C(issn)",
                    data=placed, family=sm.families.NegativeBinomial()).fit()
        ci = m.conf_int()
        R["impact_model"] = {
            "north_irr": round(float(np.exp(m.params["north"])), 3),
            "north_ci": [round(float(np.exp(ci.loc["north", 0])), 3),
                         round(float(np.exp(ci.loc["north", 1])), 3)],
            "north_p": float(m.pvalues["north"]),
            "logpop_irr": round(float(np.exp(m.params["log_pop"])), 3),
            "n": int(m.nobs)}
    except Exception as e:
        R["impact_model_error"] = str(e)

    # ---- B. topic x geography ---------------------------------------------
    text = load_text_by_eid(set(placed["eid"]))
    placed["text"] = placed["eid"].map(text).fillna("")
    rows = []
    for topic, pat in TOPICS.items():
        rx = re.compile(pat, re.IGNORECASE)
        sub = placed[placed["text"].str.contains(rx)]
        if len(sub) < 30:
            continue
        cc = sub.groupby(["study_city", "study_country"]).size()
        rows.append({"topic": topic, "n": int(len(sub)),
                     "pct_north": round(100*sub["north"].mean(), 1),
                     "pct_africa": round(100*(sub["continent"] == "Africa").mean(), 1),
                     "gini": round(float(gini(cc.values)), 3),
                     "top_city": f"{cc.idxmax()[0]}, {cc.idxmax()[1]}"})
    tdf = pd.DataFrame(rows).sort_values("pct_north")
    R["topic_geography"] = tdf.to_dict("records")
    tdf.to_csv(config.PROCESSED / "topic_geography.csv", index=False)

    (config.PROCESSED / "results.json").write_text(json.dumps(R, indent=2, default=str))
    print("== A. Citation equity ==")
    print(f"  mean citations: North-city {R['impact_mean_north']} vs South-city {R['impact_mean_south']}")
    if "impact_model" in R:
        im = R["impact_model"]
        print(f"  NB (n={im['n']}, controls: year+journal+continent+log-pop): "
              f"North-city IRR={im['north_irr']} CI{im['north_ci']} p={im['north_p']:.1e}")
    print("\n== B. Topic x geography (sorted by % Global North) ==")
    for d in R["topic_geography"]:
        print(f"  {d['topic']:26} n={d['n']:>5}  North={d['pct_north']:>5}%  "
              f"Africa={d['pct_africa']:>4}%  Gini={d['gini']}  top={d['top_city']}")

if __name__ == "__main__":
    main()
