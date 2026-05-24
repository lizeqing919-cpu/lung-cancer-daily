"""Shared helpers: dedup tracking, article scoring, logging."""

import json
import logging
import os
from pathlib import Path

from scripts import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---- PMID Dedup ----

def load_seen_pmids():
    """Load {pmid: date_str} map. Returns empty dict if file missing or corrupt."""
    f = config.SEEN_PMIDS_FILE
    if os.path.exists(f):
        try:
            return json.loads(open(f, "r", encoding="utf-8").read())
        except (json.JSONDecodeError, IOError):
            log.warning("seen_pmids.json corrupt, starting fresh")
    return {}


def save_seen_pmids(seen):
    os.makedirs(os.path.dirname(config.SEEN_PMIDS_FILE), exist_ok=True)
    with open(config.SEEN_PMIDS_FILE, "w", encoding="utf-8") as fh:
        json.dump(seen, fh, indent=2, ensure_ascii=False)


def mark_pmids_seen(pmids, date_str):
    seen = load_seen_pmids()
    for pmid in pmids:
        if pmid not in seen:
            seen[pmid] = date_str
    save_seen_pmids(seen)


def filter_new_pmids(pmids):
    """Return only PMIDs not previously seen."""
    seen = load_seen_pmids()
    return [p for p in pmids if p not in seen]


# ---- Journal IF Lookup ----

def load_journal_if():
    """Load journal IF lookup table. Returns dict keyed by lowercased journal name."""
    f = config.JOURNAL_IF_FILE
    if os.path.exists(f):
        try:
            return json.loads(open(f, "r", encoding="utf-8").read())
        except (json.JSONDecodeError, IOError):
            log.warning("journal_if.json missing or corrupt")
    return {}


def lookup_journal_if(journal_name, journal_if_db=None):
    """Return (impact_factor, quartile) for a journal name.
    Tries ISO abbreviation first, then full name.
    Returns (0.0, "Q4") if not found.
    """
    if journal_if_db is None:
        journal_if_db = load_journal_if()
    if not journal_name or not journal_if_db:
        return 0.0, "Q4"
    key = journal_name.strip().lower()
    info = journal_if_db.get(key)
    if info:
        return info.get("if", 0.0), info.get("quartile", "Q4")
    return 0.0, "Q4"


# ---- Scoring ----

def score_article(article):
    """Compute highlight score from journal tier + publication type bonus."""
    journal = article.get("journal", "").lower()
    tier_score = 10
    for score_val, names in config.JOURNAL_TIERS.items():
        if any(name in journal for name in names):
            tier_score = score_val
            break

    pubtype_score = 0
    for pt in article.get("pubtypes", []):
        pt_lower = pt.lower().strip()
        pubtype_score = max(pubtype_score, config.PUBTYPE_SCORE_BONUS.get(pt_lower, 0))

    return tier_score + pubtype_score
