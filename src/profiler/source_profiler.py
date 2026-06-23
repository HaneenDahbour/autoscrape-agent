"""
source_profiler.py — Probe the target URL before choosing an extraction strategy.

Purpose:
  Make a single HTTP GET request and analyse the response to build a profile
  of the source. The strategy selector uses this profile to decide which
  extractor to run.

Detections:
  - Content type (HTML / JSON / XML)
  - JavaScript-heavy pages (many <script> tags, little visible text)
  - Pagination signals (rel="next", .next link, .pagination)
  - Field-aware data visibility: evidence is detected per requested field,
    not by a raw character count. This means even a minimal page like
    example.com correctly returns data_visible_in_html=True when "title"
    or "url" are requested, because the page has a <title> and <a href>.
  - Blocking status codes (401, 403, 429)

Field evidence rules:
  "title"        → soup.title exists, OR h1/h2/h3 tags exist, OR links have text
  "url"/"href"   → any a[href] links present
  "price"        → currency symbol/code + number pattern in body text
  "availability" → availability keywords in body text
  generic field  → field name found anywhere in body text (fallback)

We identify as "AutoScrapeAgent/1.0" so operators can allow/block us.
"""

import re
import requests
from bs4 import BeautifulSoup
from src.models import JobContext

USER_AGENT = "AutoScrapeAgent/1.0"
REQUEST_TIMEOUT = 10      # seconds
JS_SCRIPT_THRESHOLD = 5   # script tags above this = potentially JS-heavy

# Matches currency symbols/codes adjacent to a number.
# Covers common international currencies.
_PRICE_RE = re.compile(
    r"(\$|€|£|¥|USD|EUR|GBP|JOD|SAR|AED|EGP|CAD|AUD)\s*[\d,]+\.?\d*"
    r"|[\d,]+\.?\d*\s*(USD|EUR|GBP|JOD|SAR|AED|EGP|CAD|AUD)",
    re.IGNORECASE,
)

# Common availability-indicator phrases
_AVAILABILITY_RE = re.compile(
    r"\b(available|in[\s-]stock|out[\s-]of[\s-]stock|sold[\s-]out"
    r"|ships|unavailable|pre[\s-]order|back[\s-]order)\b",
    re.IGNORECASE,
)

# Fields that map to the "url" evidence check
_URL_FIELD_NAMES = {"url", "href", "link"}

# Fields that map to the "title" evidence check
_TITLE_FIELD_NAMES = {"title", "name", "heading"}


def _detect_field_evidence(
    soup: BeautifulSoup,
    fields: list[str],
    body_text: str,
) -> tuple[list[str], int, int, int]:
    """
    For each requested field, look for field-specific evidence in the parsed HTML.

    Returns:
      visible_field_hits    — field names for which evidence was found
      link_count            — total number of a[href] elements
      title_candidates_count — number of h1/h2/h3 elements
      price_candidates_count — number of price pattern matches in body text
    """
    link_count = len(soup.find_all("a", href=True))
    title_candidates = len(soup.find_all(["h1", "h2", "h3"]))
    price_matches = _PRICE_RE.findall(body_text)
    price_candidates = len(price_matches)

    hits: list[str] = []

    for raw_field in fields:
        field = raw_field.lower().strip()

        if field in _TITLE_FIELD_NAMES:
            # Evidence: page has a <title>, or heading tags, or any link with text
            has_page_title = soup.title is not None and bool(soup.title.string)
            has_headings = title_candidates > 0
            has_link_text = any(
                a.get_text(strip=True) for a in soup.find_all("a", href=True)
            )
            if has_page_title or has_headings or has_link_text:
                hits.append(field)

        elif field in _URL_FIELD_NAMES:
            # Evidence: any clickable link exists
            if link_count > 0:
                hits.append(field)

        elif field == "price":
            # Evidence: currency pattern found in text
            if price_candidates > 0:
                hits.append(field)

        elif field == "availability":
            # Evidence: availability keyword found in text
            if _AVAILABILITY_RE.search(body_text):
                hits.append(field)

        else:
            # Generic fallback: field name appears literally in body text
            if field in body_text.lower():
                hits.append(field)

    return hits, link_count, title_candidates, price_candidates


def run_source_profiler(ctx: JobContext) -> JobContext:
    """
    Fetch the target URL and populate ctx.source_profile.

    Blocks (sets ctx.allowed=False) on HTTP 401, 403, 429.
    Appends a decision to ctx.decisions.

    New profile keys added in this version:
      visible_field_hits       — list of fields that had detectable evidence
      link_count               — number of a[href] elements on the page
      title_candidates_count   — number of h1/h2/h3 elements
      price_candidates_count   — number of price-pattern matches (0 if not requested)
    """
    # Skip if already blocked
    if not ctx.allowed:
        ctx.decisions.append({
            "layer": "source_profiler",
            "decision": "skipped",
            "reason": "Job already blocked by a previous layer; profiling skipped.",
        })
        return ctx

    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(ctx.url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        error = f"Network error while profiling {ctx.url}: {exc}"
        ctx.errors.append(error)
        ctx.allowed = False
        ctx.source_profile = {"error": error}
        ctx.decisions.append({
            "layer": "source_profiler",
            "decision": "blocked",
            "reason": error,
        })
        return ctx

    status_code = response.status_code
    content_type = response.headers.get("Content-Type", "").lower()
    html_size = len(response.content)

    # ── Blocking status codes ────────────────────────────────────────────────
    if status_code in (401, 403, 429):
        reason_map = {
            401: "401 Unauthorized — page requires login. AutoScrape does not scrape login-required pages.",
            403: "403 Forbidden — server explicitly denied access.",
            429: "429 Too Many Requests — rate limited. Stopping to be a good citizen.",
        }
        reason = reason_map[status_code]
        ctx.allowed = False
        ctx.authorization_status = "blocked"
        ctx.errors.append(reason)
        ctx.source_profile = {
            "status_code": status_code,
            "content_type": content_type,
            "html_size": html_size,
            "is_json": False, "is_xml": False, "is_html": False,
            "js_heavy": False, "pagination_detected": False,
            "data_visible_in_html": False,
            "visible_field_hits": [],
            "link_count": 0,
            "title_candidates_count": 0,
            "price_candidates_count": 0,
        }
        ctx.decisions.append({
            "layer": "source_profiler",
            "decision": "blocked",
            "reason": reason,
        })
        return ctx

    # ── Content type detection ───────────────────────────────────────────────
    is_json = "application/json" in content_type or "text/json" in content_type
    is_xml = "application/xml" in content_type or "text/xml" in content_type
    is_html = "text/html" in content_type

    # ── HTML analysis (only if HTML) ─────────────────────────────────────────
    js_heavy = False
    pagination_detected = False
    data_visible_in_html = False
    visible_field_hits: list[str] = []
    link_count = 0
    title_candidates_count = 0
    price_candidates_count = 0

    if is_html:
        soup = BeautifulSoup(response.text, "lxml")
        body_text = soup.get_text(separator=" ", strip=True)

        # JS-heavy: many script tags AND very little visible text on the page.
        # Note: we check script count against visible text length, not field evidence.
        # A page can be JS-heavy even if it has a <title>.
        script_count = len(soup.find_all("script"))
        js_heavy = script_count > JS_SCRIPT_THRESHOLD and len(body_text) < 200

        # Pagination signals
        has_rel_next = bool(soup.find("a", rel="next"))
        has_class_next = bool(soup.find("a", class_="next"))
        has_pagination_div = bool(soup.select(".pagination a"))
        pagination_detected = has_rel_next or has_class_next or has_pagination_div

        # ── Field-aware evidence detection ───────────────────────────────────
        # data_visible_in_html is True when at least one requested field
        # has detectable evidence in the HTML. This replaces the old raw
        # character-count check, which was too strict for simple pages.
        (
            visible_field_hits,
            link_count,
            title_candidates_count,
            price_candidates_count,
        ) = _detect_field_evidence(soup, ctx.fields, body_text)

        data_visible_in_html = len(visible_field_hits) > 0

    profile = {
        "status_code": status_code,
        "content_type": content_type,
        "html_size": html_size,
        "is_json": is_json,
        "is_xml": is_xml,
        "is_html": is_html,
        "js_heavy": js_heavy,
        "pagination_detected": pagination_detected,
        "data_visible_in_html": data_visible_in_html,
        # ── New fields ────────────────────────────────────────────────────────
        "visible_field_hits": visible_field_hits,
        "link_count": link_count,
        "title_candidates_count": title_candidates_count,
        "price_candidates_count": price_candidates_count,
    }
    ctx.source_profile = profile

    reason = (
        f"Profiled {ctx.url}: status={status_code}, "
        f"is_html={is_html}, is_json={is_json}, is_xml={is_xml}, "
        f"js_heavy={js_heavy}, pagination={pagination_detected}, "
        f"data_visible={data_visible_in_html}, "
        f"field_hits={visible_field_hits}, links={link_count}."
    )
    ctx.decisions.append({
        "layer": "source_profiler",
        "decision": "profiled",
        "reason": reason,
    })
    return ctx
