"""Generate static HTML for the daily brief, archive snapshots, and archive index."""

import json
import os
from datetime import datetime, timezone, timedelta
from html import escape

from scripts import config
from scripts.utils import log

TAG_LABELS = {
    "targeted therapy": ("靶向治疗", "tag-targeted"),
    "immunotherapy": ("免疫治疗", "tag-immunotherapy"),
    "surgery": ("外科手术", "tag-surgery"),
    "radiotherapy": ("放疗", "tag-radiotherapy"),
    "chemotherapy": ("化疗", "tag-chemotherapy"),
    "supportive care": ("支持治疗", "tag-supportive"),
}

PATHOLOGY_LABELS = {
    "NSCLC": "非小细胞肺癌 (NSCLC)",
    "SCLC": "小细胞肺癌 (SCLC)",
    "Lymph Node": "淋巴结研究",
    "Other": "其他",
}


def _tag_html(tag):
    label, css_class = TAG_LABELS.get(tag, (tag, "tag-other"))
    return f'<span class="tag {css_class}">{escape(label)}</span>'


def _article_card(art):
    """Render one article card as HTML."""
    pmid = art.get("pmid", "")
    title = art.get("title", "No title")
    journal = art.get("journal", "")
    pubdate = art.get("pubdate", "")
    abstract = art.get("abstract", "")
    conclusion = art.get("chinese_conclusion", "")
    treatment_tags = art.get("treatment_tags", [])
    keywords = art.get("chinese_keywords", [])
    jif = art.get("journal_if", 0)
    quartile = art.get("journal_quartile", "")
    score = art.get("highlight_score", 0)
    source = art.get("source", "core")
    authors = art.get("authors", "")

    # Truncate abstract for card display
    abstract_excerpt = abstract[:350]
    if len(abstract) > 350:
        abstract_excerpt += "..."

    # IF + Quartile badge
    if jif and jif > 0:
        if_badge = f'<span class="if-badge">{jif:.1f}</span>'
    else:
        if_badge = ""
    if quartile:
        quartile_badge = f'<span class="quartile-badge quartile-{quartile.lower()}">{quartile}</span>'
    else:
        quartile_badge = ""

    # Source badge
    source_badge = ""
    if source == "fallback":
        source_badge = '<span class="source-badge" title="补充文章">🔄 补充</span>'

    # PMID link
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    # Tags
    tags_html = " ".join(_tag_html(t) for t in treatment_tags)

    # Keywords
    kw_html = ""
    if keywords:
        kw_spans = " ".join(
            f'<span class="keyword">{escape(k)}</span>' for k in keywords
        )
        kw_html = f'<div class="card-keywords">{kw_spans}</div>'

    return f"""<article class="card" data-score="{score}" data-source="{source}">
  <div class="card-header">
    <h3 class="card-title">
      <a href="{pubmed_url}" target="_blank" rel="noopener">{escape(title)}</a>
    </h3>
    <div class="card-meta">
      <span class="card-journal">{escape(journal)}</span>
      {if_badge}
      {quartile_badge}
      <span class="card-date">{pubdate}</span>
      {source_badge}
    </div>
    {f'<div class="card-authors">{escape(authors)}</div>' if authors else ''}
  </div>
  <p class="card-abstract">{escape(abstract_excerpt)}</p>
  {kw_html}
  <div class="card-conclusion">
    <span class="conclusion-label">关键结论</span>
    <p>{escape(conclusion)}</p>
  </div>
  <div class="card-tags">{tags_html}</div>
</article>"""


def _render_daily(articles, date_str):
    """Render today's brief page from articles list."""
    # Split: highlights vs rest
    articles_sorted = sorted(articles, key=lambda a: a.get("highlight_score", 0), reverse=True)

    highlight_count = min(config.HIGHLIGHT_COUNT_MAX,
                          max(config.HIGHLIGHT_COUNT_MIN, len(articles_sorted)))
    highlights = articles_sorted[:highlight_count]
    rest = articles_sorted[highlight_count:]

    # Group rest by pathology
    groups = {"NSCLC": [], "SCLC": [], "Lymph Node": [], "Other": []}
    for art in rest:
        path = art.get("pathology", "Other")
        if path not in groups:
            path = "Other"
        groups[path].append(art)

    # Render highlights
    highlights_html = "\n".join(_article_card(a) for a in highlights)

    # Render each pathology section
    sections_html = ""
    for path_key in ["NSCLC", "SCLC", "Lymph Node", "Other"]:
        group_articles = groups[path_key]
        if not group_articles:
            continue
        cards = "\n".join(_article_card(a) for a in group_articles)
        label = PATHOLOGY_LABELS.get(path_key, path_key)
        sections_html += f"""
  <section class="pathology-section">
    <h2 class="section-header">{label} ({len(group_articles)} 篇)</h2>
    <div class="cards">
      {cards}
    </div>
  </section>"""

    # Total count
    total = len(articles)

    # Build content HTML
    if total == 0:
        content_html = '<div class="empty-state">今日无新发表文献。请稍后查看。</div>'
    else:
        highlight_count = len(highlights)
        content_html = f"""<details id="highlight-section" open>
    <summary class="section-header section-highlight">
      <h2>重点推荐 ({highlight_count} 篇)</h2>
    </summary>
    <div class="cards">
      {highlights_html}
    </div>
  </details>

  <details id="full-list" open>
    <summary class="section-header">
      <h2>完整列表</h2>
    </summary>
    {sections_html}
  </details>"""

    # Read template
    template_path = os.path.join(config.TEMPLATES_DIR, "daily.html")
    with open(template_path, "r", encoding="utf-8") as fh:
        template = fh.read()

    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")

    # Countdown data as JS variable
    import json as _json
    countdown_json = _json.dumps(config.UPCOMING_CONFERENCES, ensure_ascii=False)
    countdown_script = f"<script>window.__COUNTDOWN_DATA__ = {countdown_json};</script>"

    html = template.replace("{{date}}", date_str)
    html = html.replace("{{generated_at}}", generated_at)
    html = html.replace("{{article_count}}", str(total))
    html = html.replace("{{countdown_script}}", countdown_script)
    html = html.replace("{{content_html}}", content_html)

    return html


def _rebuild_archive_index():
    """Rebuild archive/index.html from all archive subdirectories."""
    archive_dirs = []
    archive_root = config.ARCHIVE_DIR
    if os.path.isdir(archive_root):
        for name in os.listdir(archive_root):
            path = os.path.join(archive_root, name)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "index.html")):
                archive_dirs.append(name)

    archive_dirs.sort(reverse=True)

    # Group by year-month
    rows_html = ""
    current_ym = None
    for d in archive_dirs:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        ym = dt.strftime("%Y-%m")
        if ym != current_ym:
            if current_ym is not None:
                rows_html += "</ul>\n"
            current_ym = ym
            rows_html += f'<h3 class="archive-month">{ym}</h3>\n<ul class="archive-list">\n'
        rows_html += (
            f'  <li><a href="{d}/">{d}</a></li>\n'
        )

    if current_ym is not None:
        rows_html += "</ul>\n"

    if not rows_html:
        rows_html = '<p class="empty-state">暂无归档。</p>'

    template_path = os.path.join(config.TEMPLATES_DIR, "archive.html")
    with open(template_path, "r", encoding="utf-8") as fh:
        template = fh.read()

    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")

    html = template.replace("{{generated_at}}", generated_at)
    html = html.replace("{{archive_rows_html}}", rows_html)

    return html


def main():
    date_str = config.get_date_str()
    summarized_path = os.path.join(config.SUMMARIZED_DIR, f"{date_str}.json")

    if not os.path.exists(summarized_path):
        log.info("No summarized data for %s, checking fetched data...", date_str)
        # Try fetched data as fallback (when summarizer hasn't run)
        fetched_path = os.path.join(config.FETCHED_DIR, f"{date_str}.json")
        if os.path.exists(fetched_path):
            with open(fetched_path, "r", encoding="utf-8") as fh:
                articles = json.load(fh)
        else:
            articles = []
    else:
        with open(summarized_path, "r", encoding="utf-8") as fh:
            articles = json.load(fh)

    log.info("Generating HTML for %d articles", len(articles))

    # Generate today's page
    daily_html = _render_daily(articles, date_str)
    with open(config.INDEX_FILE, "w", encoding="utf-8") as fh:
        fh.write(daily_html)
    log.info("Wrote %s", config.INDEX_FILE)

    # Archive snapshot
    archive_day_dir = os.path.join(config.ARCHIVE_DIR, date_str)
    os.makedirs(archive_day_dir, exist_ok=True)
    archive_path = os.path.join(archive_day_dir, "index.html")
    with open(archive_path, "w", encoding="utf-8") as fh:
        fh.write(daily_html)
    log.info("Wrote %s", archive_path)

    # Rebuild archive index
    archive_index_html = _rebuild_archive_index()
    archive_index_path = os.path.join(config.ARCHIVE_DIR, "index.html")
    with open(archive_index_path, "w", encoding="utf-8") as fh:
        fh.write(archive_index_html)
    log.info("Wrote %s", archive_index_path)

    log.info("=== HTML generation complete ===")


if __name__ == "__main__":
    main()
