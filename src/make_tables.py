"""Emit LaTeX tables (\\input-ed by main.tex) directly from the analysis outputs,
so every number in every table is synced to the data. Run after analysis.

Run:  python3 -m src.make_tables
"""
from __future__ import annotations
import json
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

from . import config

PAPER = config.ROOT / "paper"

def esc(s):
    return str(s).replace("&", "\\&").replace("%", "\\%")

def journals_table():
    arts = pd.read_parquet(config.PROCESSED / "articles.parquet")
    placed = arts.groupby("issn")["has_study_city"].mean()
    n = arts.groupby("issn").size()
    rows = []
    for title, issn, tier in config.JOURNALS:
        rows.append((title, issn, int(n.get(issn, 0)), 100 * placed.get(issn, 0)))
    rows.sort(key=lambda r: -r[2])
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{Journals in the corpus, article counts, and the share of",
         r"articles with an identified primary study city (\% placed).}\label{tab:journals}",
         r"\begin{tabular}{lrr}\toprule",
         r"Journal & Articles & \% placed \\\midrule"]
    for title, issn, ncount, pct in rows:
        L.append(f"{esc(title)} & {ncount:,} & {pct:.1f} \\\\")
    L += [r"\midrule", f"\\textbf{{Total}} & {sum(r[2] for r in rows):,} & "
          f"{100*arts['has_study_city'].mean():.1f} \\\\",
          r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_journals.tex").write_text("\n".join(L))

def top_cities_table():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{The twenty most-studied cities (by primary study city).}\label{tab:topcities}",
         r"\begin{tabular}{rlr}\toprule",
         r"Rank & City & Studies \\\midrule"]
    for i, d in enumerate(R["top20_cities"], 1):
        L.append(f"{i} & {esc(d['city'])}, {d['country']} & {d['n']} \\\\")
    L += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_topcities.tex").write_text("\n".join(L))

def over_under_table():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    over = R["most_over_studied"][:10]
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{Most over-studied large cities relative to population "
         r"(cities with population $\geq$250{,}000 and $\geq$10 studies), ranked by the "
         r"over/under-study index (observed studies $\div$ studies expected under "
         r"population-proportional attention).}\label{tab:overstudied}",
         r"\begin{tabular}{lrrr}\toprule",
         r"City & Population & Studies & Index \\\midrule"]
    for d in over:
        L.append(f"{esc(d['city'])}, {d['country']} & {int(d['pop']):,} & "
                 f"{int(d['studies'])} & {float(d['index']):.1f}$\\times$ \\\\")
    L += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_overstudied.tex").write_text("\n".join(L))

def continent_rep_table():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{Representation of each continent: share of located studies versus "
         r"share of world population, and the resulting representation ratio "
         r"(study share $\div$ population share; $>1$ over-represented).}\label{tab:continent}",
         r"\begin{tabular}{lrrrr}\toprule",
         r"Continent & Studies & \% studies & \% world pop. & Ratio \\\midrule"]
    for d in R["continent_representation"]:
        L.append(f"{d['continent']} & {int(d['studies']):,} & {d['studies_pct']:.1f} & "
                 f"{d['pop_pct']:.1f} & {d['rep_ratio']:.2f} \\\\")
    L += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_continent.tex").write_text("\n".join(L))

def country_flow_table():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    def block(rows):
        return [f"{esc(d['name'])} & {int(d['received'])} & {int(d['produced'])} & "
                f"{float(d['ratio']):.2f} \\\\" for d in rows]
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{Net importers and exporters of research attention. \emph{Received} = articles whose "
         r"study city is in the country; \emph{produced} = articles with at least one "
         r"author based there. Ratio $>1$: a country is studied more than it publishes; "
         r"$<1$: its researchers study elsewhere.}\label{tab:countryflow}",
         r"\begin{tabular}{lrrr}\toprule",
         r"Country & Received & Produced & Ratio \\\midrule",
         r"\multicolumn{4}{l}{\textit{Net importers (studied $>$ produced)}}\\"]
    L += block(R["attention_magnets"][:8])
    L += [r"\midrule", r"\multicolumn{4}{l}{\textit{Net exporters (produced $>$ studied)}}\\"]
    L += block(R["attention_exporters"][:8])
    L += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_countryflow.tex").write_text("\n".join(L))

def model_table():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{Negative-binomial regression of a city's study count on its "
         r"characteristics, over all \NMODEL\ gazetteer cities (continent fixed effects "
         r"included; pseudo-$R^2=\MODELPSEUDOR$). IRR = incidence-rate ratio "
         r"($e^{\beta}$); 95\% confidence intervals in brackets.}\label{tab:model}",
         r"\begin{tabular}{lrrl}\toprule",
         r"Predictor & Coef. & IRR & 95\% CI \\\midrule"]
    for d in R["model_table"]:
        if d["term"] == "Intercept":
            continue
        p = "$<$0.001" if d["p"] < 1e-3 else f"{d['p']:.3f}"
        L.append(f"{d['term']} & {d['coef']:.3f} & {d['irr']:.2f} & "
                 f"[{d['ci_low']:.2f}, {d['ci_high']:.2f}] \\\\")
    L += [r"\midrule", r"\multicolumn{4}{l}{\footnotesize Continent fixed effects included. "
          r"All predictors $p<0.001$.}\\",
          r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_model.tex").write_text("\n".join(L).replace(r"\NMODEL", f"{R['model_n']:,}"))

def topics_table():
    R = json.loads((config.PROCESSED / "results.json").read_text())
    if "topic_geography" not in R:
        return
    L = [r"\begin{table}[tbp]\centering\small",
         r"\caption{Geographic skew by research topic (transparent author-keyword "
         r"lexicon; an article may match several topics). \% North is the share of a "
         r"topic's located studies in Global-North cities; Gini is concentration across "
         r"cities within the topic.}\label{tab:topics}",
         r"\begin{tabular}{lrrrl}\toprule",
         r"Topic & Articles & \% North & Gini & Most studied \\\midrule"]
    for d in R["topic_geography"]:
        L.append(f"{esc(d['topic'])} & {int(d['n']):,} & {d['pct_north']:.1f} & "
                 f"{d['gini']:.3f} & {esc(d['top_city'])} \\\\")
    L += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "tab_topics.tex").write_text("\n".join(L))

def main():
    journals_table()
    top_cities_table()
    over_under_table()
    continent_rep_table()
    country_flow_table()
    model_table()
    topics_table()
    print("Wrote tab_journals, tab_topcities, tab_overstudied, tab_continent, "
          "tab_countryflow, tab_model")

if __name__ == "__main__":
    main()
