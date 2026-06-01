# Where Transportation Research Looks

Code and data for a city-level audit of which cities are studied across 18 Elsevier
transport and urban journals (58,714 articles), and the gap between where research is
conducted and where its authors are based.

## Repository layout
- `src/` — analysis pipeline (Python)
- `data/raw/scopus/` — harvested article metadata, one JSONL per journal ISSN
- `data/processed/` — extracted tables, `results.json`, validation labels, model outputs
- `data/external/` — GeoNames gazetteer, country info, World Bank indicators

## Setup
```bash
pip install -r requirements.txt
```
Re-harvesting from Scopus requires Elsevier credentials, read from
`~/.config/elsevier/{apikey,insttoken}` (never committed). The released `data/` lets the
analysis be reproduced without re-harvesting.

## Pipeline (run in order)
```bash
python3 -m src.validate            # validate ISSNs, corpus sizes, entitlement
python3 -m src.harvest             # Scopus metadata -> data/raw/scopus/*.jsonl (resumable)
python3 -m src.gazetteer           # GeoNames cities15000 -> filtered gazetteer.json
python3 -m src.extract             # study-city + author-city -> data/processed/*.parquet
python3 -m src.sample_for_labeling 120   # blind validation sample
python3 -m src.score_validation    # precision / recall / F1, city accuracy
python3 -m src.analysis            # Gini, over/under-study, 2x2 typology, NB model, figures
python3 -m src.topics_impact       # topic x geography; citation-equity model
python3 -m src.robust_stats        # GDP/urbanization model, zero-inflated NB, Theil
python3 -m src.finalize_results    # validation + robustness into results.json
```
`src/make_macros.py` and `src/make_tables.py` emit LaTeX inputs for the manuscript,
which is maintained separately.

## Key design choices (see code comments)
- **Rate limits:** per-second throttle + `X-RateLimit-Remaining` guard + resumable
  per-journal checkpoints (`src/elsevier_client.py`, `src/harvest.py`).
- **Geoparsing precision:** dictionary + population + multi-word-phrase filtering of the
  gazetteer, plus a documented benchmark-network exclusion (`src/gazetteer.py`).
- **Validation:** independent blind LLM annotation of 120 articles (F1 = 0.81, city
  accuracy 0.97 given detection); high-precision title/keyword subset as robustness.
- **References:** every citation verified against Crossref (`src/build_bib.py`).

## Data provenance and licensing
Article metadata are derived from Elsevier Scopus via the Scopus Search API and are
subject to Elsevier's terms of use. City data are from GeoNames (CC BY); national
indicators from the World Bank (CC BY 4.0); reference metadata from Crossref.
