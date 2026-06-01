"""Project configuration: target journals, API endpoints, credential loading.

Cities-in-transportation-research study.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_SCOPUS = DATA / "raw" / "scopus"
RAW_FULLTEXT = DATA / "raw" / "fulltext"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"

# --- Credentials -----------------------------------------------------------
# Loaded from env first, then ~/.config/elsevier/{apikey,insttoken}.
def _load_secret(env_name: str, filename: str) -> str | None:
    val = os.environ.get(env_name)
    if val:
        return val.strip()
    p = Path.home() / ".config" / "elsevier" / filename
    if p.exists():
        return p.read_text().strip()
    return None

API_KEY = _load_secret("ELSEVIER_API_KEY", "apikey")
INST_TOKEN = _load_secret("ELS_INSTTOKEN", "insttoken")

# --- Endpoints -------------------------------------------------------------
SCOPUS_SEARCH = "https://api.elsevier.com/content/search/scopus"
ARTICLE_RETRIEVAL = "https://api.elsevier.com/content/article/doi/"   # + DOI
ABSTRACT_RETRIEVAL = "https://api.elsevier.com/content/abstract/scopus_id/"

# Per-API throttle (requests/second) and weekly quota, from dev.elsevier.com.
THROTTLE = {"scopus_search": 9, "sciencedirect_search": 2,
            "article_retrieval": 10, "abstract_retrieval": 9}
WEEKLY_QUOTA = {"scopus_search": 20000, "sciencedirect_search": 20000,
                "article_retrieval": 50000, "abstract_retrieval": 10000}

# --- Target journals (Elsevier transport-core + urban-relevant) ------------
# 'tier': core = clearly transportation; urban = transport-relevant but broad.
# ISSNs validated against the API in scripts/01_validate_issns.py.
JOURNALS = [
    # title, print ISSN, tier
    ("Journal of Transport Geography",                              "0966-6923", "core"),
    ("Transport Policy",                                            "0967-070X", "core"),
    ("Transportation Research Part A: Policy and Practice",         "0965-8564", "core"),
    ("Transportation Research Part B: Methodological",              "0191-2615", "core"),
    ("Transportation Research Part C: Emerging Technologies",       "0968-090X", "core"),
    ("Transportation Research Part D: Transport and Environment",   "1361-9209", "core"),
    ("Transportation Research Part E: Logistics and Transp. Rev.",  "1366-5545", "core"),
    ("Transportation Research Part F: Traffic Psych. and Behaviour","1369-8478", "core"),
    ("Transportation Research Interdisciplinary Perspectives",      "2590-1982", "core"),
    ("Travel Behaviour and Society",                               "2214-367X", "core"),
    ("Case Studies on Transport Policy",                           "2213-624X", "core"),
    ("Journal of Rail Transport Planning & Management",            "2210-9706", "core"),
    ("Research in Transportation Economics",                       "0739-8859", "core"),
    ("Research in Transportation Business & Management",           "2210-5395", "core"),
    ("Journal of Air Transport Management",                        "0969-6997", "core"),
    ("International Journal of Transp. Science and Technology",     "2046-0430", "core"),
    # Urban-general but heavily transport; decide inclusion after first cut.
    ("Cities",                                                     "0264-2751", "urban"),
    ("Sustainable Cities and Society",                             "2210-6707", "urban"),
]

CORE_ISSNS = [issn for _, issn, tier in JOURNALS if tier == "core"]
ALL_ISSNS = [issn for _, issn, _ in JOURNALS]
