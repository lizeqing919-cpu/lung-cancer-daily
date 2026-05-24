"""Centralised configuration for the lung-cancer-daily pipeline."""

import os
from datetime import datetime, timedelta, timezone

# ---- PubMed Query ----

# Part A: Core clinical lung cancer query
QUERY_PART_A_TEMPLATE = (
    '(lung cancer[Title/Abstract] OR lung neoplasms[MeSH Terms] '
    'OR NSCLC[Title/Abstract] OR SCLC[Title/Abstract] '
    'OR "non-small cell lung"[Title/Abstract] OR "small cell lung"[Title/Abstract]) '
    'AND (clinical trial[Publication Type] '
    'OR randomized controlled trial[Publication Type] '
    'OR meta-analysis[Publication Type] '
    'OR guideline[Publication Type] '
    'OR practice guideline[Publication Type] '
    'OR systematic review[Publication Type]) '
    'AND ("{date_from}"[Date - Publication] : "{date_to}"[Date - Publication])'
)

# Part B: Lymph node specific query (no publication type filter)
QUERY_PART_B_TEMPLATE = (
    '(lung cancer[Title/Abstract] OR lung neoplasms[MeSH Terms] '
    'OR NSCLC[Title/Abstract] OR SCLC[Title/Abstract]) '
    'AND (lymph node[Title/Abstract] OR "lymph node dissection"[Title/Abstract] '
    'OR "lymph node staging"[Title/Abstract] '
    'OR "sentinel lymph node"[Title/Abstract] OR "mediastinal lymph node"[Title/Abstract] '
    'OR "nodal metastasis"[Title/Abstract] OR lymphadenectomy[Title/Abstract] '
    'OR "lymph node metastasis"[Title/Abstract] OR N-staging[Title/Abstract] '
    'OR "lymph node ratio"[Title/Abstract] OR mediastinoscopy[Title/Abstract] '
    'OR EBUS[Title/Abstract]) '
    'AND ("{date_from}"[Date - Publication] : "{date_to}"[Date - Publication])'
)

# Part C: Fallback query (7-day window, clinical filter)
QUERY_PART_C_TEMPLATE = (
    '(lung cancer[Title/Abstract] OR lung neoplasms[MeSH Terms] '
    'OR NSCLC[Title/Abstract] OR SCLC[Title/Abstract]) '
    'AND (clinical trial[Publication Type] '
    'OR randomized controlled trial[Publication Type] '
    'OR meta-analysis[Publication Type] '
    'OR guideline[Publication Type] '
    'OR practice guideline[Publication Type] '
    'OR systematic review[Publication Type]) '
    'AND ("{date_from}"[Date - Publication] : "{date_to}"[Date - Publication])'
)

DATE_RANGE_DAYS = 2  # window for Part A & B
FALLBACK_DATE_RANGE_DAYS = 7  # window for Part C fallback

# ---- Article Thresholds ----

MIN_DAILY_ARTICLES = 10
MIN_JOURNAL_IF = 4.0  # minimum IF for fallback articles
HIGHLIGHT_COUNT_MIN = 5
HIGHLIGHT_COUNT_MAX = 8

# ---- Journal Tier Scoring ----

JOURNAL_TIERS = {
    100: [
        "n engl j med", "lancet", "jama", "bmj",
    ],
    80: [
        "j clin oncol", "lancet oncol", "jama oncol",
        "ann oncol", "cancer discov", "lancet respir med",
    ],
    60: [
        "j thorac oncol", "clin cancer res", "cancer res",
        "lung cancer", "chest", "thorax", "eur respir j",
        "int j radiat oncol biol phys", "radiotherapy oncol",
        "j natl cancer inst", "nat rev clin oncol",
    ],
    40: [
        "eur j cancer", "cancer", "br j cancer",
        "radiology", "chest surg clin n am",
        "transl lung cancer res", "clin lung cancer",
        "j cancer res clin oncol", "oncol",
        "cancer lett", "cancer med",
    ],
}

PUBTYPE_SCORE_BONUS = {
    "guideline": 50,
    "practice guideline": 50,
    "meta-analysis": 40,
    "randomized controlled trial": 40,
    "systematic review": 30,
    "clinical trial, phase iii": 30,
    "clinical trial, phase ii": 15,
}

# ---- DeepSeek API ----

DEEPSEEK_MODEL = "deepseek-v4-pro"  # highest-capability model
DEEPSEEK_BATCH_SIZE = 10
DEEPSEEK_MAX_TOKENS_PER_ARTICLE = 300

# ---- PubMed E-utilities ----

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_RETMAX = 200
PUBMED_SLEEP_SEC = 0.5  # without API key (3 req/sec limit); 0.15 with key

# ---- Paths ----

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FETCHED_DIR = os.path.join(DATA_DIR, "fetched")
SUMMARIZED_DIR = os.path.join(DATA_DIR, "summarized")
SEEN_PMIDS_FILE = os.path.join(DATA_DIR, "seen_pmids.json")
JOURNAL_IF_FILE = os.path.join(DATA_DIR, "journal_if.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")


def get_date_str(days_ago=0):
    """Return date string YYYY-MM-DD for today minus `days_ago` in China time (UTC+8)."""
    tz = timezone(timedelta(hours=8))
    dt = datetime.now(tz) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


def get_date_range(days=DATE_RANGE_DAYS):
    """Return (date_from, date_to) in YYYY/MM/DD format for a days-wide window."""
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    date_to = today.strftime("%Y/%m/%d")
    date_from = (today - timedelta(days=days)).strftime("%Y/%m/%d")
    return date_from, date_to
