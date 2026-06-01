"""Emit LaTeX \\newcommand macros for every headline number, from results.json.
Keeps the manuscript numbers in exact sync with the analysis (no hand-copying).

Run:  python3 -m src.make_macros   ->  paper/results_macros.tex
"""
from __future__ import annotations
import json
from . import config

def comma(n):
    return f"{int(round(float(n))):,}"

def main():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    L = []
    def cmd(name, val):
        L.append(f"\\newcommand{{\\{name}}}{{{val}}}")

    cmd("NARTICLES", comma(R["n_articles"]))
    cmd("NPLACED", comma(R["n_placed"]))
    cmd("PCTPLACED", f"{R['pct_placed']}\\%")
    cmd("NDISTINCTCITIES", comma(R["n_distinct_cities"]))
    cmd("NDISTINCTCOUNTRIES", comma(R["n_distinct_countries"]))
    cmd("NJOURNALS", str(len(config.JOURNALS)))
    cmd("GINI", f"{R['gini_cities']}")
    cmd("TOPTENSHARE", f"{R['top10_share']}\\%")
    cmd("TOPTWENTYSHARE", f"{R['top20_share']}\\%")
    cmd("PCTNORTHSTUDIES", f"{R['pct_global_north_studies']}\\%")
    cmd("PCTLOCAL", f"{R['pct_local_studies']}\\%")
    cmd("PCTSOUTHBYNORTH", f"{R['pct_south_studied_by_allnorth']}\\%")
    cmd("PCTNORTHBYNORTH", f"{R['pct_north_studied_by_allnorth']}\\%")
    if "model_irr" in R:
        # 2 dp to match the regression table (Table~\ref{tab:model})
        cmd("IRRPOP", f"{R['model_irr']['log_pop']:.2f}")
        cmd("IRRNORTH", f"{R['model_irr']['north']:.2f}")
        cmd("IRRENGLISH", f"{R['model_irr']['english']:.2f}")
        cmd("MODELN", comma(R["model_n"]))
        cmd("MODELPSEUDOR", f"{R['model_pseudo_r2']}")
    # quadrant counts
    q = R.get("quad_counts", {})
    for key in ("over_local", "over_outsider", "under_local", "under_outsider"):
        cmd("Q" + key.upper().replace("_", ""), str(q.get(key, 0)))

    # under-study headline
    cmd("NCITIESOVERM", comma(R["n_cities_over_1m"]))
    cmd("PCTZEROSTUDIES", f"{R['pct_over_1m_zero_studies']}\\%")
    cmd("PCTLEQONESTUDY", f"{R['pct_over_1m_leq1_study']}\\%")

    # continent shares
    cb = R.get("studies_by_continent", {})
    for cont in ("Asia", "Europe", "North America", "South America", "Oceania", "Africa"):
        cmd("CONT" + cont.replace(" ", "").upper(), comma(cb.get(cont, 0)))

    # continental representation ratios
    for d in R.get("continent_representation", []):
        nm = d["continent"].replace(" ", "").upper()
        cmd("REP" + nm, f"{d['rep_ratio']}")
    cmd("MODELN", comma(R["model_n"]))

    # validation
    v = R.get("validation", {})
    if v:
        cmd("VALN", str(v["n"]))
        cmd("VALPREC", f"{v['precision']}")
        cmd("VALREC", f"{v['recall']}")
        cmd("VALFONE", f"{v['f1']}")
        cmd("VALCITYACC", f"{int(round(v['city_accuracy_given_detection']*100))}\\%")
        cmd("VALTP", str(v["tp"])); cmd("VALFP", str(v["fp"]))
        cmd("VALFN", str(v["fn"])); cmd("VALTN", str(v["tn"]))

    # temporal trends (first vs last full 5-year period: 1990 vs 2020)
    tr = {t["period"]: t for t in R.get("trend", [])}
    if 1990 in tr and 2020 in tr:
        cmd("GINIEARLY", f"{tr[1990]['gini']}")
        cmd("GINILATE", f"{tr[2020]['gini']}")
        cmd("NORTHEARLY", f"{tr[1990]['pct_north']}\\%")
        cmd("NORTHLATE", f"{tr[2020]['pct_north']}\\%")
        cmd("AFRICAEARLY", f"{tr[1990]['pct_africa']}\\%")
        cmd("AFRICALATE", f"{tr[2020]['pct_africa']}\\%")

    # robustness
    rb = R.get("robustness", {})
    if rb:
        cmd("GINIANCHORED", f"{rb['gini_anchored']}")
        cmd("TOPTWENTYANCHORED", f"{rb['top20_share_anchored']}\\%")
        cmd("TOPTWENTYOVERLAP", str(rb["top20_overlap"]))
        cmd("ANCHOREDSHARE", f"{rb['anchored_share_of_placed']}\\%")

    # A. citation impact
    im = R.get("impact_model", {})
    if im:
        cmd("IMPACTNORTHIRR", f"{im['north_irr']}")
        cmd("IMPACTNORTHCILO", f"{im['north_ci'][0]}")
        cmd("IMPACTNORTHCIHI", f"{im['north_ci'][1]}")
        cmd("IMPACTN", comma(im["n"]))
    if "impact_mean_north" in R:
        cmd("IMPACTMEANNORTH", f"{R['impact_mean_north']}")
        cmd("IMPACTMEANSOUTH", f"{R['impact_mean_south']}")

    # B. topic extremes (topic_geography is sorted ascending by % North)
    tg = R.get("topic_geography", [])
    if tg:
        cmd("TOPICMINNORTH", f"{tg[0]['pct_north']}\\%")
        cmd("TOPICMINNAME", tg[0]["topic"])
        cmd("TOPICMAXNORTH", f"{tg[-1]['pct_north']}\\%")
        cmd("TOPICMAXNAME", tg[-1]["topic"])
        cmd("TOPICMAXGINI", f"{tg[-1]['gini']}")

    # C. wealth model, ZINB, Theil
    mw = R.get("model_wealth", {})
    if mw:
        cmd("WEALTHNORTHIRR", f"{mw['north_irr']}")
        cmd("WEALTHNORTHCILO", f"{mw['north_ci'][0]}")
        cmd("WEALTHNORTHCIHI", f"{mw['north_ci'][1]}")
        cmd("GDPIRR", f"{mw['gdppc_irr']}")
        cmd("WEALTHN", comma(mw["n"]))
    if "model_zinb_north_irr" in R:
        cmd("ZINBNORTHIRR", f"{R['model_zinb_north_irr']}")
    if "theil_total" in R:
        cmd("THEILTOTAL", f"{R['theil_total']}")
        cmd("THEILWITHINPCT", f"{R['theil_pct_within']}\\%")

    # D. full-text recall
    ft = R.get("fulltext", {})
    if ft:
        cmd("FTNRETRIEVED", comma(ft["n_retrieved"]))
        cmd("FTAGREE", f"{int(round(ft['primary_agreement']*100))}\\%")
        cmd("FTRECALLGAP", f"{int(round(ft['recall_gap_metadata_none_placed_by_fulltext']*100))}\\%")
        cmd("FTGINIMETA", f"{ft['gini_metadata_sample']}")
        cmd("FTGINIFT", f"{ft['gini_fulltext_sample']}")
        cmd("FTOVERLAP", str(ft["top20_overlap"]))

    (config.ROOT / "paper" / "results_macros.tex").write_text("\n".join(L) + "\n")
    print(f"Wrote {len(L)} macros to paper/results_macros.tex")

if __name__ == "__main__":
    main()
