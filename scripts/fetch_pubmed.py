"""Fetch lung cancer clinical articles from PubMed E-utilities API.

Pipeline:
  Part A — core clinical query (2-day window, publication type filter)
  Part B — lymph node query (2-day window, no PT filter)
  If combined < MIN_DAILY_ARTICLES:
    Part C — fallback (7-day window, clinical filter, IF >= 4)
"""

import json
import os
import sys
import time
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests
from lxml import etree

from scripts import config
from scripts.utils import (
    filter_new_pmids,
    log,
    load_journal_if,
    mark_pmids_seen,
    score_article,
)

NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")


def _esearch(query, retmax=None):
    """Run esearch, return list of PMID strings."""
    if retmax is None:
        retmax = config.PUBMED_RETMAX
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(retmax),
        "sort": "date",
        "datetype": "pdat",
        "retmode": "json",
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    url = config.PUBMED_ESEARCH_URL + "?" + urlencode(params)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("esearchresult", {}).get("idlist", [])


def _efetch(pmids):
    """Fetch full XML records for a list of PMIDs. Returns lxml root."""
    if not pmids:
        return None
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    resp = requests.post(
        config.PUBMED_EFETCH_URL,
        data=params,
        timeout=60,
    )
    resp.raise_for_status()
    return etree.fromstring(resp.content)


def _parse_articles(xml_root):
    """Parse efetch XML into list of article dicts."""
    articles = []
    if xml_root is None:
        return articles

    for pa in xml_root.findall(".//PubmedArticle"):
        mc = pa.find("MedlineCitation")
        if mc is None:
            continue

        pmid_el = mc.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else ""

        article_el = mc.find("Article")
        if article_el is None:
            continue

        title_el = article_el.find("ArticleTitle")
        title = title_el.text or "" if title_el is not None else ""

        # Abstract
        abstract_parts = []
        abs_el = article_el.find("Abstract")
        if abs_el is not None:
            for at in abs_el.findall("AbstractText"):
                label = at.get("Label", "")
                text = etree.tostring(at, method="text", encoding="unicode").strip()
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # Journal name (prefer ISO abbreviation)
        journal_el = article_el.find("Journal")
        journal = ""
        if journal_el is not None:
            iso_el = journal_el.find("ISOAbbreviation")
            if iso_el is not None and iso_el.text:
                journal = iso_el.text
            else:
                title_j = journal_el.find("Title")
                if title_j is not None and title_j.text:
                    journal = title_j.text

        # PubDate -> YYYY-MM-DD
        pubdate = _extract_pubdate(journal_el)

        # Publication types
        pubtypes = []
        pt_list = article_el.find("PublicationTypeList")
        if pt_list is not None:
            for pt in pt_list.findall("PublicationType"):
                if pt.text:
                    pubtypes.append(pt.text)

        # Authors (first 3 + et al.)
        authors = _extract_authors(article_el)

        # Keywords (MeSH + author keywords)
        keywords = _extract_keywords(mc)

        # DOI
        doi = ""
        eid_list = article_el.find("ELocationID")
        if eid_list is not None:
            eid = eid_list
            if eid.get("EIdType") == "doi" and eid.text:
                doi = eid.text

        articles.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "pubdate": pubdate,
            "pubtypes": pubtypes,
            "authors": authors,
            "keywords": keywords,
            "doi": doi,
            "source": "core",  # "core" or "fallback"
        })

    return articles


def _extract_pubdate(journal_el):
    """Extract publication date as YYYY-MM-DD string."""
    if journal_el is None:
        return ""
    jid = journal_el.find("JournalIssue")
    if jid is None:
        return ""
    pd_el = jid.find("PubDate")
    if pd_el is None:
        return ""

    year = _text(pd_el, "Year")
    month = _text(pd_el, "Month", default="01")
    day = _text(pd_el, "Day", default="01")

    # Convert month name to number
    month_names = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    month_lower = month.lower()[:3]
    month = month_names.get(month_lower, "01")

    day = day.zfill(2)
    if year and month and day:
        return f"{year}-{month}-{day}"
    return ""


def _text(parent, tag, default=""):
    el = parent.find(tag)
    return el.text if el is not None and el.text else default


def _extract_authors(article_el):
    """Extract first 3 authors + et al. string."""
    al = article_el.find("AuthorList")
    if al is None:
        return ""
    authors = []
    for a in al.findall("Author"):
        ln = _text(a, "LastName")
        fn = _text(a, "ForeName")
        if ln:
            name = ln
            if fn:
                name = f"{fn} {ln}"
            authors.append(name)
    if len(authors) <= 3:
        return ", ".join(authors)
    return ", ".join(authors[:3]) + ", et al."


def _extract_keywords(mc):
    """Extract MeSH headings and author keywords."""
    kw = []

    # MeSH terms
    mh_list = mc.find("MeshHeadingList")
    if mh_list is not None:
        for mh in mh_list.findall("MeshHeading"):
            desc = mh.find("DescriptorName")
            if desc is not None and desc.text:
                kw.append(desc.text)

    # Author keywords
    kw_list = mc.find("KeywordList")
    if kw_list is not None:
        for k in kw_list.findall("Keyword"):
            if k.text:
                kw.append(k.text)

    return kw[:15]  # cap at 15 keywords


def fetch_part(query_template, days, label):
    """Run a single query part, return (pmids, articles)."""
    date_from, date_to = config.get_date_range(days=days)
    query = query_template.format(date_from=date_from, date_to=date_to)
    log.info("[%s] Searching PubMed: window=%s to %s", label, date_from, date_to)
    log.info("[%s] Query: %s...", label, query[:200])

    pmids = _esearch(query)
    log.info("[%s] esearch returned %d PMIDs", label, len(pmids))

    new_pmids = filter_new_pmids(pmids)
    log.info("[%s] %d are new (not previously seen)", label, len(new_pmids))

    if not new_pmids:
        return [], []

    articles = []
    # Batch fetch in groups of 100 (PubMed limit)
    for i in range(0, len(new_pmids), 100):
        batch = new_pmids[i:i + 100]
        sleep_s = 0.15 if NCBI_API_KEY else config.PUBMED_SLEEP_SEC
        time.sleep(sleep_s)
        try:
            xml_root = _efetch(batch)
            parsed = _parse_articles(xml_root)
            articles.extend(parsed)
            log.info("[%s] Fetched batch %d-%d: %d articles",
                     label, i, i + len(batch), len(parsed))
        except Exception as exc:
            log.error("[%s] efetch failed for batch %d: %s", label, i, exc)

    return new_pmids, articles


def fetch_part_c_fallback(existing_pmids, journal_if_db):
    """Fallback: 7-day clinical query, filter by IF >= 4, return top articles."""
    date_from, date_to = config.get_date_range(days=config.FALLBACK_DATE_RANGE_DAYS)
    query = config.QUERY_PART_C_TEMPLATE.format(date_from=date_from, date_to=date_to)
    log.info("[PartC] Fallback search: 7-day window, IF >= %.1f", config.MIN_JOURNAL_IF)

    pmids = _esearch(query)
    existing_set = set(existing_pmids)
    new_pmids = [p for p in pmids if p not in existing_set]
    new_pmids = filter_new_pmids(new_pmids)
    log.info("[PartC] Found %d new PMIDs in 7-day window", len(new_pmids))

    if not new_pmids:
        return [], []

    # Fetch all
    articles = []
    for i in range(0, len(new_pmids), 100):
        batch = new_pmids[i:i + 100]
        sleep_s = 0.15 if NCBI_API_KEY else config.PUBMED_SLEEP_SEC
        time.sleep(sleep_s)
        try:
            xml_root = _efetch(batch)
            parsed = _parse_articles(xml_root)
            articles.extend(parsed)
        except Exception as exc:
            log.error("[PartC] efetch failed for batch %d: %s", i, exc)

    # Filter by IF >= 4
    qualified = []
    for art in articles:
        jif, quartile = lookup_journal_if_cached(art["journal"], journal_if_db)
        if jif >= config.MIN_JOURNAL_IF:
            art["journal_if"] = jif
            art["journal_quartile"] = quartile
            art["source"] = "fallback"
            qualified.append(art)

    # Sort by IF descending
    qualified.sort(key=lambda a: a.get("journal_if", 0), reverse=True)

    log.info("[PartC] %d articles qualify with IF >= %.1f", len(qualified), config.MIN_JOURNAL_IF)
    return [a["pmid"] for a in qualified], qualified


def lookup_journal_if_cached(journal_name, journal_if_db):
    """Lookup IF/quartile with our local cache."""
    if not journal_name:
        return 0.0, "Q4"
    key = journal_name.strip().lower()
    info = journal_if_db.get(key)
    if info:
        return info.get("if", 0.0), info.get("quartile", "Q4")
    return 0.0, "Q4"


def main():
    """Main fetch pipeline."""
    date_str = config.get_date_str()
    log.info("=== Daily fetch for %s ===", date_str)

    journal_if_db = load_journal_if()
    log.info("Loaded %d journals in IF database", len(journal_if_db))

    # Part A: Core clinical
    pmids_a, articles_a = fetch_part(config.QUERY_PART_A_TEMPLATE, config.DATE_RANGE_DAYS, "PartA")
    log.info("Part A: %d articles", len(articles_a))

    # Rate-limit pause between parts (PubMed: 3 req/sec without API key)
    time.sleep(1.5)

    # Part B: Lymph node
    pmids_b, articles_b = fetch_part(config.QUERY_PART_B_TEMPLATE, config.DATE_RANGE_DAYS, "PartB")
    log.info("Part B (lymph node): %d articles", len(articles_b))

    # Merge & dedup by PMID
    all_articles = {a["pmid"]: a for a in articles_a}
    for a in articles_b:
        if a["pmid"] not in all_articles:
            all_articles[a["pmid"]] = a
    all_pmids_seen = set(pmids_a) | set(pmids_b)

    log.info("Combined unique articles (Part A+B): %d", len(all_articles))

    # Part C: Fallback if below threshold
    if len(all_articles) < config.MIN_DAILY_ARTICLES:
        shortage = config.MIN_DAILY_ARTICLES - len(all_articles)
        log.info("Below minimum (%d < %d). Running fallback...",
                 len(all_articles), config.MIN_DAILY_ARTICLES)
        time.sleep(1.5)  # rate-limit before Part C
        pmids_c, articles_c = fetch_part_c_fallback(all_pmids_seen, journal_if_db)

        # Take only what's needed
        for a in articles_c[:shortage]:
            if a["pmid"] not in all_articles:
                all_articles[a["pmid"]] = a

        log.info("After fallback: %d total articles", len(all_articles))

    # Enrich with journal IF & score
    article_list = list(all_articles.values())
    for art in article_list:
        jif, quartile = lookup_journal_if_cached(art["journal"], journal_if_db)
        art["journal_if"] = jif
        art["journal_quartile"] = quartile
        art["highlight_score"] = score_article(art)

    # Sort by highlight score descending
    article_list.sort(key=lambda a: a["highlight_score"], reverse=True)

    # Mark all PMIDs as seen
    mark_pmids_seen([a["pmid"] for a in article_list], date_str)

    # Write fetched data
    os.makedirs(config.FETCHED_DIR, exist_ok=True)
    out_path = os.path.join(config.FETCHED_DIR, f"{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(article_list, fh, indent=2, ensure_ascii=False)

    log.info("Saved %d articles to %s", len(article_list), out_path)

    # Write empty signal if zero articles
    if len(article_list) == 0:
        log.info("No new articles today. Generating empty page signal.")
        empty_signal = os.path.join(config.DATA_DIR, "empty_today")
        with open(empty_signal, "w") as fh:
            fh.write(date_str)

    # Remove empty signal if articles found
    empty_signal = os.path.join(config.DATA_DIR, "empty_today")
    if os.path.exists(empty_signal) and len(article_list) > 0:
        os.remove(empty_signal)

    log.info("=== Fetch complete: %d new articles ===", len(article_list))
    return article_list


if __name__ == "__main__":
    main()
