"""
static_html_extractor.py — Extract data from static HTML pages.

Strategy: static_html
Implemented: V1

Method:
  1. Fetch the page with requests (same User-Agent as profiler).
  2. Parse with BeautifulSoup.
  3. Extract all <a> tags as items:
       title = anchor text (stripped)
       url   = href attribute
       source = "static_html"
  4. If no links are found, fall back to the page <title> as a single item.

This extractor does NOT:
  - Handle JavaScript-rendered content.
  - Follow pagination.
  - Log in or handle CAPTCHAs.
"""

import requests
from bs4 import BeautifulSoup
from src.models import JobContext

USER_AGENT = "AutoScrapeAgent/1.0"
REQUEST_TIMEOUT = 10


def run_static_html_extractor(ctx: JobContext) -> JobContext:
    """
    Extract link items from a static HTML page.

    Populates ctx.raw_items.
    Appends a decision to ctx.decisions.
    """
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(ctx.url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        error = f"static_html_extractor: network error fetching {ctx.url}: {exc}"
        ctx.errors.append(error)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "error",
            "reason": error,
        })
        return ctx

    soup = BeautifulSoup(response.text, "lxml")

    # ── Primary extraction: all anchor tags ───────────────────────────────────
    items = []
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        href = anchor["href"].strip()

        # Skip empty or javascript: links
        if not href or href.startswith("javascript:") or href == "#":
            continue

        items.append({
            "title": text or href,   # use href as title if text is empty
            "url": href,
            "source": "static_html",
        })

    # ── Fallback: use the page title ─────────────────────────────────────────
    if not items:
        page_title = soup.title.string.strip() if soup.title and soup.title.string else ctx.url
        items.append({
            "title": page_title,
            "url": ctx.url,
            "source": "static_html_fallback",
        })

    ctx.raw_items = items
    reason = (
        f"Extracted {len(items)} raw item(s) from {ctx.url} "
        f"using static HTML extraction (requests + BeautifulSoup)."
    )
    ctx.decisions.append({
        "layer": "extractor",
        "decision": "extracted",
        "reason": reason,
    })
    return ctx
