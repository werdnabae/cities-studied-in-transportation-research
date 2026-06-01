"""Part C: rigor upgrades that need no annotation.
  * World Bank GDP-per-capita and urbanization covariates added to the study-count
    model (does the Global-North effect survive controlling for wealth?).
  * Zero-inflated negative binomial as a robustness check for the mass of zeros.
  * Theil index decomposed into between- and within-continent inequality.
  * Bootstrap 95% CI for the Gini of study attention.

Run:  python3 -m src.robust_stats
"""
from __future__ import annotations
import json, urllib.request
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from . import config, countries

WB = {"gdppc": "NY.GDP.PCAP.CD", "urban": "SP.URB.TOTL.IN.ZS"}

def wb_fetch(indicator):
    cache = config.EXTERNAL / f"wb_{indicator}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    flat = {}
    url = (f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
           f"?format=json&date=2021&per_page=400")
    page = json.loads(urllib.request.urlopen(url, timeout=12).read())  # one quick try
    for d in (page[1] or []):
        i3, v = d.get("countryiso3code"), d.get("value")
        if i3 and v is not None and i3 not in flat:
            flat[i3] = v
    cache.write_text(json.dumps(flat))
    return flat

def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    if n == 0 or x.sum() == 0: return float("nan")
    return (2*np.sum((np.arange(1, n+1))*x)/(n*x.sum())) - (n+1)/n

def theil_decomp(df):
    """Theil-T of `studies` across cities, decomposed by continent."""
    x = df["studies"].values.astype(float)
    N, m = len(x), x.mean()
    nz = x > 0
    T = (1/N) * np.sum((x[nz]/m) * np.log(x[nz]/m))
    Tb = 0.0; Tw = 0.0
    for _, g in df.groupby("continent"):
        xg = g["studies"].values.astype(float)
        Ng, mg = len(xg), xg.mean()
        if mg <= 0: continue
        Tb += (Ng/N) * (mg/m) * np.log(mg/m)
        nzg = xg > 0
        Tg = (1/Ng) * np.sum((xg[nzg]/mg) * np.log(xg[nzg]/mg)) if nzg.any() else 0.0
        Tw += (Ng/N) * (mg/m) * Tg
    return T, Tb, Tw

def main():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    idx = pd.read_csv(config.PROCESSED / "over_under_study.csv")  # all gaz cities
    idx["continent"] = idx["country"].map(countries.continent)
    idx["north"] = idx["country"].map(countries.is_global_north).fillna(False).astype(int)
    idx["english"] = idx["country"].map(countries.is_english).astype(int)
    idx["log_pop"] = np.log10(idx["pop"].clip(lower=1))

    import statsmodels.formula.api as smf
    import statsmodels.api as sm
    # ---- World Bank covariates (optional; skipped if API unreachable) ------
    try:
        gdp = wb_fetch(WB["gdppc"]); urb = wb_fetch(WB["urban"])
        iso2_gdp = {countries.iso3_to_iso2(i3): v for i3, v in gdp.items()}
        iso2_urb = {countries.iso3_to_iso2(i3): v for i3, v in urb.items()}
        idx["log_gdppc"] = np.log10(idx["country"].map(iso2_gdp))
        idx["urban"] = idx["country"].map(iso2_urb)
        dfm = idx.dropna(subset=["log_gdppc", "urban"]).copy()
        m = smf.glm("studies ~ log_pop + log_gdppc + urban + north + english + C(continent)",
                    data=dfm, family=sm.families.NegativeBinomial()).fit()
        ci = m.conf_int()
        R["model_wealth"] = {
            "n": int(m.nobs),
            "north_irr": round(float(np.exp(m.params["north"])), 3),
            "north_ci": [round(float(np.exp(ci.loc["north", 0])), 3),
                         round(float(np.exp(ci.loc["north", 1])), 3)],
            "gdppc_irr": round(float(np.exp(m.params["log_gdppc"])), 3)}
    except Exception as e:
        R["model_wealth_skipped"] = "World Bank API unreachable in this environment"

    # ---- zero-inflated NB robustness --------------------------------------
    try:
        from patsy import dmatrices
        y, X = dmatrices("studies ~ log_pop + north + english + C(continent)",
                         data=idx, return_type="dataframe")
        zinb = sm.ZeroInflatedNegativeBinomialP(
            y, X, exog_infl=X[["Intercept"]]).fit(method="bfgs", maxiter=200, disp=0)
        R["model_zinb_north_irr"] = round(float(np.exp(zinb.params["north"])), 3)
    except Exception as e:
        R["model_zinb_error"] = str(e)[:160]

    # ---- Theil decomposition ----------------------------------------------
    T, Tb, Tw = theil_decomp(idx.dropna(subset=["continent"]))
    R["theil_total"] = round(float(T), 3)
    R["theil_between_continent"] = round(float(Tb), 3)
    R["theil_within_continent"] = round(float(Tw), 3)
    R["theil_pct_within"] = round(100*Tw/T, 1)

    # ---- bootstrap Gini CI (resample articles) ----------------------------
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    placed = arts.dropna(subset=["study_city"])
    codes = placed.groupby(["study_city", "study_country"]).ngroup().values
    K = codes.max() + 1
    rng = np.random.RandomState(42)
    boots = []
    n = len(codes)
    for _ in range(400):
        samp = codes[rng.randint(0, n, n)]
        c = np.bincount(samp, minlength=K)
        boots.append(gini(c[c > 0]))   # Gini over cities that appear, matching point estimate
    R["gini_boot_ci"] = [round(float(np.percentile(boots, 2.5)), 3),
                         round(float(np.percentile(boots, 97.5)), 3)]

    (config.PROCESSED / "results.json").write_text(json.dumps(R, indent=2, default=str))
    print("Wealth model:", R.get("model_wealth", R.get("model_wealth_skipped")))
    print("ZINB north IRR:", R.get("model_zinb_north_irr", R.get("model_zinb_error")))
    print(f"Theil total={R['theil_total']} between-cont={R['theil_between_continent']} "
          f"within-cont={R['theil_within_continent']} ({R['theil_pct_within']}% within)")
    print(f"Gini={R['gini_cities']} 95% CI {R['gini_boot_ci']}")

if __name__ == "__main__":
    main()
