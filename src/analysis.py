"""Core analysis + figures for the cities-in-transport-research paper.

Produces (data/processed/ and paper/figs/, paper/results.md):
  * coverage + concentration (Gini, Lorenz, top-N share)
  * top studied cities / countries
  * population-normalized over/under-study index (full-gazetteer expectation)
  * author-vs-study gap: local vs outsider study, North/South parachute flows
  * 2x2 typology (over/under-studied x studied-by-locals/outsiders)
  * negative-binomial model: what predicts a city's study count?

Run:  python3 -m src.analysis
"""
from __future__ import annotations
import json
import warnings; warnings.filterwarnings("ignore")
from collections import Counter

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Keep in-figure fonts close to the manuscript caption size (\footnotesize).
plt.rcParams.update({"font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8,
                     "ytick.labelsize": 8, "legend.fontsize": 8})
COMMA = mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
from . import config, countries

FIGS = config.ROOT / "paper" / "figs"
FIGS.mkdir(parents=True, exist_ok=True)
R = {}  # results dict for the draft

def gini(x):
    x = np.sort(np.asarray(x, float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return float("nan")
    return (2 * np.sum((np.arange(1, n + 1)) * x) / (n * x.sum())) - (n + 1) / n

def load():
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    gaz = json.loads((config.PROCESSED / "gazetteer.json").read_text())
    # city -> (country, pop): collapse gazetteer keys to canonical cities, taking
    # the MAX population for a given (city, country) so a same-named small town
    # never shrinks the denominator of a large metro.
    citypop = {}
    for v in gaz.values():
        k = (v["city"], v["country"])
        if k not in citypop or v["pop"] > citypop[k]:
            citypop[k] = v["pop"]
    return arts, citypop

def author_iso2(raw_countries):
    out = set()
    if raw_countries is None:
        return out
    try:
        seq = list(raw_countries)
    except TypeError:
        return out
    for n in seq:
        i = countries.to_iso2(n)
        if i:
            out.add(i)
    return out

def main():
    arts, citypop = load()
    placed = arts.dropna(subset=["study_city"]).copy()
    R["n_articles"] = int(len(arts))
    R["n_placed"] = int(len(placed))
    R["pct_placed"] = round(100 * len(placed) / len(arts), 1)
    R["n_distinct_cities"] = int(placed.groupby(["study_city", "study_country"]).ngroups)
    R["n_distinct_countries"] = int(placed["study_country"].nunique())

    # ---- concentration -----------------------------------------------------
    counts = placed.groupby(["study_city", "study_country"]).size().sort_values(ascending=False)
    R["gini_cities"] = round(float(gini(counts.values)), 3)
    for k in (10, 20, 50):
        R[f"top{k}_share"] = round(100 * counts.head(k).sum() / counts.sum(), 1)
    R["top20_cities"] = [{"city": c, "country": ct, "n": int(n)}
                         for (c, ct), n in counts.head(20).items()]

    # Lorenz curve
    cum = np.cumsum(np.sort(counts.values)) / counts.sum()
    xs = np.linspace(0, 1, len(cum))
    plt.figure(figsize=(4.2, 4.2))
    plt.plot(xs, cum, lw=2, label=f"cities (Gini={R['gini_cities']})")
    plt.plot([0, 1], [0, 1], "k--", lw=1, label="equality")
    plt.xlabel("cumulative share of studied cities")
    plt.ylabel("cumulative share of studies")
    plt.legend(); plt.tight_layout(); plt.savefig(FIGS / "lorenz_cities.png", dpi=160); plt.close()

    # top-20 bar
    top = counts.head(20)[::-1]
    plt.figure(figsize=(5.2, 6))
    plt.barh([f"{c}" for c, _ in top.index], top.values)
    plt.xlabel("number of studies (primary city)")
    plt.tight_layout(); plt.savefig(FIGS / "top20_cities.png", dpi=160); plt.close()

    # ---- geography of studies (continent / North-South) --------------------
    placed["study_continent"] = placed["study_country"].map(countries.continent)
    placed["study_north"] = placed["study_country"].map(countries.is_global_north)
    cont = placed["study_continent"].value_counts()
    R["studies_by_continent"] = {k: int(v) for k, v in cont.items()}
    R["pct_global_north_studies"] = round(100 * placed["study_north"].mean(), 1)

    plt.figure(figsize=(5, 3.2))
    cont.sort_values().plot(kind="barh")
    plt.xlabel("number of studies")
    plt.gca().xaxis.set_major_formatter(COMMA)
    plt.tight_layout()
    plt.savefig(FIGS / "studies_by_continent.png", dpi=160); plt.close()

    # ---- population-normalized over/under-study (full-gazetteer expectation)
    total_studies = counts.sum()
    total_pop = sum(citypop.values())
    rows = []
    for (c, ct), pop in citypop.items():
        obs = int(counts.get((c, ct), 0))
        exp = total_studies * pop / total_pop if total_pop else 0
        rows.append({"city": c, "country": ct, "pop": pop, "studies": obs,
                     "expected": exp, "index": (obs / exp) if exp > 0 else np.nan})
    idx = pd.DataFrame(rows)
    idx.to_csv(config.PROCESSED / "over_under_study.csv", index=False)
    # Over-studied table: restrict to genuinely large cities (>=250k) so the
    # ranking reflects real over-attention rather than same-name disambiguation
    # artifacts among tiny towns.
    idx_studied = idx[(idx.studies >= 10) & (idx["pop"] >= 250_000)].sort_values("index", ascending=False)
    R["most_over_studied"] = idx_studied.head(15)[["city", "country", "pop", "studies", "index"]].to_dict("records")
    big_under = idx[(idx["pop"] >= 1_000_000)].sort_values("index")
    R["most_under_studied_big"] = big_under.head(15)[["city", "country", "pop", "studies", "index"]].to_dict("records")
    # Robust headline: share of large cities that are essentially unstudied.
    big = idx[idx["pop"] >= 1_000_000]
    R["n_cities_over_1m"] = int(len(big))
    R["pct_over_1m_zero_studies"] = round(100 * (big["studies"] == 0).mean(), 1)
    R["pct_over_1m_leq1_study"] = round(100 * (big["studies"] <= 1).mean(), 1)

    # ---- author-vs-study gap ----------------------------------------------
    placed["author_iso2"] = placed["author_countries_raw"].apply(author_iso2)
    placed["has_aff"] = placed["author_iso2"].apply(lambda s: len(s) > 0)
    g = placed[placed.has_aff].copy()
    g["local"] = g.apply(lambda r: r["study_country"] in r["author_iso2"], axis=1)
    R["pct_local_studies"] = round(100 * g["local"].mean(), 1)
    R["gap_coverage"] = round(100 * placed["has_aff"].mean(), 1)

    # North/South parachute: Global-South-city studies done by all-North teams
    g["study_is_south"] = ~g["study_country"].map(countries.is_global_north).fillna(False)
    g["team_all_north"] = g["author_iso2"].apply(
        lambda s: len(s) > 0 and all(countries.is_global_north(i) for i in s))
    south = g[g.study_is_south]
    R["pct_south_studied_by_allnorth"] = round(100 * south["team_all_north"].mean(), 1) if len(south) else None
    north = g[~g.study_is_south]
    R["pct_north_studied_by_allnorth"] = round(100 * north["team_all_north"].mean(), 1) if len(north) else None

    # local share per city (for the 2x2)
    loc = (g.groupby(["study_city", "study_country"])
             .agg(n=("local", "size"), local_share=("local", "mean")).reset_index())
    loc = loc[loc.n >= 5].merge(
        idx[["city", "country", "index", "pop"]],
        left_on=["study_city", "study_country"], right_on=["city", "country"], how="left")
    loc.to_csv(config.PROCESSED / "city_localshare.csv", index=False)

    # 2x2 thresholds: index vs 1 (vs global pop-average), local_share vs median
    ls_med = loc["local_share"].median()
    def quad(r):
        over = r["index"] >= 1
        local = r["local_share"] >= ls_med
        return ("over" if over else "under") + "_" + ("local" if local else "outsider")
    loc["quadrant"] = loc.apply(quad, axis=1)
    R["quad_counts"] = {k: int(v) for k, v in loc["quadrant"].value_counts().items()}
    R["local_share_median"] = round(float(ls_med), 3)
    R["examples_over_outsider"] = (loc[loc.quadrant == "over_outsider"]
        .sort_values("n", ascending=False).head(10)[["study_city", "study_country", "n", "index", "local_share"]]
        .to_dict("records"))
    R["examples_over_local"] = (loc[loc.quadrant == "over_local"]
        .sort_values("n", ascending=False).head(10)[["study_city", "study_country", "n", "index", "local_share"]]
        .to_dict("records"))

    # 2x2 scatter
    plt.figure(figsize=(5.5, 4.5))
    sc = plt.scatter(np.log10(loc["index"].clip(lower=1e-3)), loc["local_share"],
                     s=np.sqrt(loc["n"]) * 6, alpha=0.5)
    plt.axvline(0, color="k", lw=0.8); plt.axhline(ls_med, color="k", lw=0.8, ls="--")
    plt.xlabel("log10 over/under-study index (0 = global pop average)")
    plt.ylabel("local-author share")
    for _, r in loc.sort_values("n", ascending=False).head(12).iterrows():
        plt.annotate(r["study_city"], (np.log10(max(r["index"], 1e-3)), r["local_share"]),
                     fontsize=7)
    plt.tight_layout(); plt.savefig(FIGS / "typology_2x2.png", dpi=160); plt.close()

    # ---- temporal trends ---------------------------------------------------
    pl = placed.dropna(subset=["year"]).copy()
    pl = pl[(pl.year >= 1990) & (pl.year <= 2025)]
    pl["period"] = (pl["year"] // 5 * 5).astype(int)
    trend = []
    for per, grp in pl.groupby("period"):
        cc = grp.groupby(["study_city", "study_country"]).size()
        trend.append({"period": int(per), "n": int(len(grp)),
                      "gini": round(float(gini(cc.values)), 3),
                      "top10_share": round(100 * cc.sort_values(ascending=False).head(10).sum() / cc.sum(), 1),
                      "pct_north": round(100 * grp["study_country"].map(countries.is_global_north).mean(), 1),
                      "pct_africa": round(100 * (grp["study_country"].map(countries.continent) == "Africa").mean(), 1)})
    tdf = pd.DataFrame(trend)
    tdf.to_csv(config.PROCESSED / "trends.csv", index=False)
    R["trend"] = tdf.to_dict("records")
    R["trend_gini_first_last"] = [tdf.iloc[0]["gini"], tdf.iloc[-1]["gini"]] if len(tdf) else None
    R["trend_north_first_last"] = [tdf.iloc[0]["pct_north"], tdf.iloc[-1]["pct_north"]] if len(tdf) else None

    fig, ax1 = plt.subplots(figsize=(5.6, 3.6))
    ax1.plot(tdf["period"], tdf["gini"], "o-", color="C0", label="Gini (concentration)")
    ax1.set_ylabel("Gini coefficient", color="C0"); ax1.set_xlabel("period (5-year)")
    ax2 = ax1.twinx()
    ax2.plot(tdf["period"], tdf["pct_north"], "s--", color="C3", label="% Global North")
    ax2.set_ylabel("% studies in Global-North cities", color="C3")
    fig.tight_layout(); fig.savefig(FIGS / "trends.png", dpi=160); plt.close(fig)

    # ---- predictive model: what predicts a city's study count? -------------
    model_df = idx.copy()
    model_df["log_pop"] = np.log10(model_df["pop"].clip(lower=1))
    model_df["north"] = model_df["country"].map(countries.is_global_north).fillna(False).astype(int)
    model_df["english"] = model_df["country"].map(countries.is_english).astype(int)
    model_df["continent"] = model_df["country"].map(countries.continent).fillna("NA")
    try:
        import statsmodels.api as sm
        import statsmodels.formula.api as smf
        m = smf.glm("studies ~ log_pop + north + english + C(continent)",
                    data=model_df, family=sm.families.NegativeBinomial()).fit()
        R["model_irr"] = {k: round(float(np.exp(v)), 3) for k, v in m.params.items()
                          if k in ("log_pop", "north", "english")}
        R["model_n"] = int(m.nobs)
        R["model_pseudo_r2"] = round(float(1 - m.deviance / m.null_deviance), 3)
        (config.PROCESSED / "model_summary.txt").write_text(str(m.summary()))
    except Exception as e:
        R["model_error"] = str(e)

    # ---- country-level: attention magnets vs exporters ---------------------
    received = placed.groupby("study_country").size()
    produced = Counter()
    for s in placed["author_iso2"]:
        for i in s:
            produced[i] += 1
    produced = pd.Series(produced)
    ctab = pd.DataFrame({"received": received}).join(
        pd.DataFrame({"produced": produced}), how="outer").fillna(0)
    ctab["name"] = [countries.name(i) for i in ctab.index]
    ctab["ratio"] = ctab["received"] / ctab["produced"].replace(0, np.nan)
    ctab = ctab[ctab["received"] >= 15]
    ctab.sort_values("received", ascending=False).to_csv(config.PROCESSED / "country_attention.csv")
    R["top_countries"] = [{"country": i, "name": ctab.loc[i, "name"], "received": int(ctab.loc[i, "received"])}
                          for i in received.sort_values(ascending=False).head(20).index if i in ctab.index]
    magnets = ctab[ctab["produced"] >= 15].sort_values("ratio", ascending=False)
    R["attention_magnets"] = magnets.head(10).reset_index().rename(columns={"index": "country"})[
        ["country", "name", "received", "produced", "ratio"]].to_dict("records")
    R["attention_exporters"] = magnets.tail(10).iloc[::-1].reset_index().rename(columns={"index": "country"})[
        ["country", "name", "received", "produced", "ratio"]].to_dict("records")

    # ---- continental representation vs population ---------------------------
    contpop = countries.continent_population()
    world = contpop.get("World", 1)
    crep = []
    for cont in ["Asia", "Europe", "North America", "South America", "Oceania", "Africa"]:
        sh_stud = cont_counts_total = R["studies_by_continent"].get(cont, 0)
        s_share = 100 * R["studies_by_continent"].get(cont, 0) / sum(R["studies_by_continent"].values())
        p_share = 100 * contpop.get(cont, 0) / world
        crep.append({"continent": cont, "studies": int(R["studies_by_continent"].get(cont, 0)),
                     "studies_pct": round(s_share, 1), "pop_pct": round(p_share, 1),
                     "rep_ratio": round(s_share / p_share, 2) if p_share else None})
    R["continent_representation"] = crep

    # ---- regional under-study among large cities ---------------------------
    idx["continent"] = idx["country"].map(countries.continent)
    bigc = idx[idx["pop"] >= 1_000_000]
    reg = []
    for cont, grp in bigc.groupby("continent"):
        if cont is None:
            continue
        reg.append({"continent": cont, "n_cities": int(len(grp)),
                    "pct_zero": round(100 * (grp["studies"] == 0).mean(), 1),
                    "median_studies": float(grp["studies"].median())})
    R["regional_understudy"] = sorted(reg, key=lambda r: -r["pct_zero"])

    # ---- full regression table ---------------------------------------------
    try:
        ci = m.conf_int()
        terms = {"Intercept": "Intercept", "log_pop": "log10 population",
                 "north": "Global North", "english": "English-speaking"}
        rt = []
        for k, label in terms.items():
            if k in m.params.index:
                rt.append({"term": label, "coef": round(float(m.params[k]), 3),
                           "se": round(float(m.bse[k]), 3),
                           "irr": round(float(np.exp(m.params[k])), 3),
                           "ci_low": round(float(np.exp(ci.loc[k, 0])), 3),
                           "ci_high": round(float(np.exp(ci.loc[k, 1])), 3),
                           "p": float(m.pvalues[k])})
        R["model_table"] = rt
        R["model_continent_fe"] = True
    except Exception as e:
        R["model_table_error"] = str(e)

    # representation-ratio figure
    cr = pd.DataFrame(crep)
    plt.figure(figsize=(5.2, 3.2))
    colors = ["C0" if x >= 1 else "C3" for x in cr["rep_ratio"]]
    plt.barh(cr["continent"], cr["rep_ratio"], color=colors)
    plt.axvline(1, color="k", lw=0.8)
    plt.xlabel("representation ratio (study share ÷ population share)")
    plt.tight_layout(); plt.savefig(FIGS / "representation_ratio.png", dpi=160); plt.close()

    # ---- write results -----------------------------------------------------
    (config.PROCESSED / "results.json").write_text(json.dumps(R, indent=2, default=str))
    md = ["# Results summary (auto-generated)", ""]
    md.append(f"- Articles analyzed: **{R['n_articles']:,}**; with a primary study city: "
              f"**{R['n_placed']:,} ({R['pct_placed']}%)**")
    md.append(f"- Distinct cities: **{R['n_distinct_cities']:,}**, countries: **{R['n_distinct_countries']}**")
    md.append(f"- Concentration: **Gini={R['gini_cities']}**; top-10 cities = "
              f"**{R['top10_share']}%** of studies, top-20 = **{R['top20_share']}%**")
    md.append(f"- Global North share of studies: **{R['pct_global_north_studies']}%**")
    md.append(f"- Local-author studies: **{R['pct_local_studies']}%** "
              f"(coverage {R['gap_coverage']}% of placed articles have affiliations)")
    md.append(f"- Global-South-city studies done by all-Global-North teams: "
              f"**{R['pct_south_studied_by_allnorth']}%** (vs {R['pct_north_studied_by_allnorth']}% for North cities)")
    md.append(f"- 2x2 quadrants: {R['quad_counts']}")
    if "model_irr" in R:
        md.append(f"- NB model (n={R['model_n']}, pseudo-R²={R['model_pseudo_r2']}): IRRs {R['model_irr']}")
    md.append("")
    md.append("## Top 20 studied cities")
    for d in R["top20_cities"]:
        md.append(f"  - {d['city']}, {d['country']}: {d['n']}")
    (config.ROOT / "paper" / "results.md").write_text("\n".join(md))

    print("\n".join(md))
    print(f"\nFigures -> {FIGS}")

if __name__ == "__main__":
    main()
