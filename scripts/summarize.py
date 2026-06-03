"""Batch-summarise articles via DeepSeek API (OpenAI-compatible).

For each article the model returns JSON with:
  - chinese_conclusion: 1-2 sentence clinical takeaway in Chinese
  - pathology: one of NSCLC / SCLC / Lymph Node / Other
  - treatment_tags: list of zero or more canonical tags
  - chinese_keywords: 3-5 Chinese keyword phrases
"""

import json
import os
import sys
import time

from openai import OpenAI

from scripts import config
from scripts.utils import log, load_journal_if, lookup_journal_if

SYSTEM_PROMPT = """You are a medical literature assistant for a Chinese clinical oncology team specialising in lung cancer.

For each lung cancer research article below, return a JSON array of objects with exactly these keys:

- "chinese_conclusion": One or two sentences in Simplified Chinese summarising the key clinically relevant finding. Use professional medical Chinese. If the article has no clear clinical conclusion (e.g. methods-only paper, preclinical study with no clinical correlate), output "本文暂无明确临床结论".
- "pathology": Choose EXACTLY ONE from ["NSCLC", "SCLC", "Lymph Node", "Other"]. Use "Lymph Node" when the primary focus is lymph node staging, dissection, sentinel node, nodal metastasis patterns, mediastinal assessment (EBUS/mediastinoscopy), or lymphadenectomy specifically in lung cancer. Use "NSCLC" for non-small cell, "SCLC" for small cell.
- "treatment_tags": A list of zero or more canonical tags from ["targeted therapy", "immunotherapy", "surgery", "radiotherapy", "chemotherapy", "supportive care"]. Choose all that apply based on the article's focus.
- "chinese_keywords": A list of 3-5 Chinese keyword phrases translated and distilled from the article's MeSH terms and author-supplied keywords. Focus on clinically relevant concepts.

Return ONLY a valid JSON array, one object per article, in the exact same order as the input articles. No other text, no markdown fences."""


def build_client():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        log.error("DEEPSEEK_API_KEY environment variable not set")
        sys.exit(1)
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )


def build_user_message(articles_batch):
    parts = []
    for i, art in enumerate(articles_batch):
        kw_str = ", ".join(art.get("keywords", [])[:10])
        parts.append(
            f"Article {i + 1}:\n"
            f"Title: {art['title']}\n"
            f"Journal: {art.get('journal', '')}\n"
            f"Publication Types: {', '.join(art.get('pubtypes', []))}\n"
            f"Keywords: {kw_str}\n"
            f"Abstract: {art.get('abstract', 'No abstract available.')}"
        )
    return "\n\n".join(parts)


def summarize_batch(client, articles_batch):
    """Send one batch to DeepSeek, return parsed list of annotation dicts."""
    user_content = build_user_message(articles_batch)

    kwargs = {
        "model": config.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": config.DEEPSEEK_MAX_TOKENS_PER_ARTICLE * len(articles_batch),
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    # v4-pro thinking mode consumes tokens before output; disable for summarization
    if "v4-pro" in config.DEEPSEEK_MODEL or "reasoner" in config.DEEPSEEK_MODEL:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        del kwargs["temperature"]  # not supported with thinking param

    response = client.chat.completions.create(**kwargs)

    raw = response.choices[0].message.content
    finish = response.choices[0].finish_reason
    if raw is None:
        log.error("DeepSeek returned None content. finish_reason=%s", finish)
        raise ValueError(f"Empty response from DeepSeek (finish_reason={finish})")
    raw = raw.strip()
    log.info("DeepSeek response finish_reason=%s, content_len=%d", finish, len(raw))

    # DeepSeek json_object mode wraps the array in a {"articles": [...]} or similar;
    # handle both direct-array and wrapped-array responses.
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Strip markdown fences if present
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)

    if isinstance(parsed, dict):
        # Unwrap: find the first list value
        for val in parsed.values():
            if isinstance(val, list):
                parsed = val
                break
    if not isinstance(parsed, list):
        log.error("DeepSeek response is not a list: %s", raw[:500])
        raise ValueError("Expected JSON array from DeepSeek")

    # Pad if too short
    while len(parsed) < len(articles_batch):
        parsed.append({
            "chinese_conclusion": "摘要生成失败",
            "pathology": "Other",
            "treatment_tags": [],
            "chinese_keywords": [],
        })

    return parsed[:len(articles_batch)]


def summarize_with_retry(client, articles_batch, max_retries=2):
    for attempt in range(max_retries):
        try:
            return summarize_batch(client, articles_batch)
        except Exception as exc:
            log.warning("DeepSeek API attempt %d/%d failed: %s",
                        attempt + 1, max_retries, exc)
            if attempt == max_retries - 1:
                log.error("All retries exhausted; returning placeholders")
                return [
                    {
                        "chinese_conclusion": "摘要生成失败",
                        "pathology": "Other",
                        "treatment_tags": [],
                        "chinese_keywords": [],
                    }
                    for _ in articles_batch
                ]
            time.sleep(5)


def main():
    date_str = config.get_date_str()
    fetched_path = os.path.join(config.FETCHED_DIR, f"{date_str}.json")

    if not os.path.exists(fetched_path):
        log.info("No fetched data for %s, skipping summarization.", date_str)
        return

    with open(fetched_path, "r", encoding="utf-8") as fh:
        articles = json.load(fh)

    if not articles:
        log.info("Zero articles, skipping summarization.")
        os.makedirs(config.SUMMARIZED_DIR, exist_ok=True)
        out_path = os.path.join(config.SUMMARIZED_DIR, f"{date_str}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump([], fh, ensure_ascii=False)
        return

    log.info("Summarising %d articles with DeepSeek...", len(articles))

    client = build_client()
    batch_size = config.DEEPSEEK_BATCH_SIZE
    all_results = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        log.info("Batch %d/%d (%d articles)", i // batch_size + 1,
                 (len(articles) - 1) // batch_size + 1, len(batch))
        results = summarize_with_retry(client, batch)
        all_results.extend(results)
        if i + batch_size < len(articles):
            time.sleep(1)  # rate-limit between batches

    # Merge results back into articles
    for art, result in zip(articles, all_results):
        art["chinese_conclusion"] = result.get("chinese_conclusion", "摘要生成失败")
        art["pathology"] = result.get("pathology", "Other")
        art["treatment_tags"] = result.get("treatment_tags", [])
        art["chinese_keywords"] = result.get("chinese_keywords", [])

    os.makedirs(config.SUMMARIZED_DIR, exist_ok=True)
    out_path = os.path.join(config.SUMMARIZED_DIR, f"{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(articles, fh, indent=2, ensure_ascii=False)

    log.info("Saved %d summarized articles to %s", len(articles), out_path)


if __name__ == "__main__":
    main()
