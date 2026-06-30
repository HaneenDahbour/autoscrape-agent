"""
scrapy_extractor.py - Crawl paginated static HTML pages with Scrapy.

Strategy: scrapy
Implemented: V3.1

This extractor is intentionally constrained:
  - starts from ctx.url only,
  - stays on the same domain,
  - follows pagination/next-page links only,
  - stops at max_pages and max_items,
  - does not bypass robots, login, CAPTCHA, 401, 403, 429, or rate limits.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from typing import Any

from bs4 import BeautifulSoup

from src.models import JobContext

try:
    import scrapy
    from scrapy import signals
    from scrapy.crawler import CrawlerProcess
except ImportError:  # pragma: no cover - exercised indirectly in envs without Scrapy.
    scrapy = None
    signals = None
    CrawlerProcess = None


USER_AGENT = "AutoScrapeAgent/1.0"
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_ITEMS = 100
BLOCKED_STATUS_CODES = {401, 403, 429}

CARD_CLASS_RE = re.compile(r"(product|item|card|listing)", re.IGNORECASE)
PAGINATION_CLASS_RE = re.compile(r"(pagination|pager|next-page)", re.IGNORECASE)
PAGINATION_HREF_RE = re.compile(
    r"([?&]page=\d+|[?&]page=|/page/\d+\b|[?&]offset=|[?&]cursor=)",
    re.IGNORECASE,
)
PRICE_RE = re.compile(
    r"(\$|\u20ac|\xa3|USD|JOD|SAR)\s*[\d,]+\.?\d*"
    r"|[\d,]+\.?\d*\s*(USD|JOD|SAR)",
    re.IGNORECASE,
)
NEXT_TEXT_VALUES = {
    "next",
    ">",
    "\xbb",
    "\u0627\u0644\u062a\u0627\u0644\u064a",
    "\u0627\u0644\u0635\u0641\u062d\u0629 \u0627\u0644\u062a\u0627\u0644\u064a\u0629",
}
URL_FIELD_NAMES = {"url", "href", "link"}
TITLE_FIELD_NAMES = {"title", "name", "heading"}


def _same_domain(url: str, allowed_domain: str) -> bool:
    return urlparse(url).netloc.lower() == allowed_domain.lower()


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _rel_contains_next(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(str(part).lower() == "next" for part in value)
    return str(value).lower() == "next"


def _class_or_id_contains_pagination(tag: Any) -> bool:
    if not hasattr(tag, "get"):
        return False

    values: list[str] = []
    class_value = tag.get("class")
    if isinstance(class_value, (list, tuple, set)):
        values.extend(str(part) for part in class_value)
    elif class_value:
        values.append(str(class_value))

    id_value = tag.get("id")
    if id_value:
        values.append(str(id_value))

    return any(PAGINATION_CLASS_RE.search(value) for value in values)


def _anchor_is_next_page(anchor: Any) -> bool:
    href = anchor.get("href", "")
    text = _clean_text(anchor.get_text(separator=" ", strip=True)).lower()
    return (
        _rel_contains_next(anchor.get("rel"))
        or text in NEXT_TEXT_VALUES
        or bool(PAGINATION_HREF_RE.search(href))
        or _class_or_id_contains_pagination(anchor)
        or any(_class_or_id_contains_pagination(parent) for parent in anchor.parents)
    )


def find_next_page_candidates(
    html: str,
    current_url: str,
    allowed_domain: str | None = None,
    visited_urls: set[str] | None = None,
) -> list[str]:
    """Return same-domain pagination URLs that have not already been visited."""
    soup = BeautifulSoup(html, "lxml")
    allowed_domain = allowed_domain or urlparse(current_url).netloc.lower()
    visited_urls = visited_urls or set()
    candidates: list[str] = []

    for anchor in soup.find_all("a", href=True):
        if not _anchor_is_next_page(anchor):
            continue

        next_url = urljoin(current_url, anchor["href"].strip())
        if not _same_domain(next_url, allowed_domain):
            continue
        if next_url in visited_urls or next_url in candidates:
            continue

        candidates.append(next_url)

    return candidates


def _requested(fields: list[str], canonical_name: str) -> bool:
    if canonical_name == "title":
        return any(field.lower().strip() in TITLE_FIELD_NAMES for field in fields)
    if canonical_name == "url":
        return any(field.lower().strip() in URL_FIELD_NAMES for field in fields)
    return any(field.lower().strip() == canonical_name for field in fields)


def _extract_title(card: Any) -> str:
    for selector in ("h1", "h2", "h3", "a", ".title"):
        node = card.select_one(selector)
        text = _clean_text(node.get_text(separator=" ", strip=True) if node else "")
        if text:
            return text
    return ""


def _extract_url(card: Any, base_url: str) -> str:
    anchor = card.find("a", href=True)
    if not anchor:
        return ""
    href = anchor["href"].strip()
    if not href or href.startswith("javascript:") or href == "#":
        return ""
    return urljoin(base_url, href)


def _extract_price(card: Any) -> str:
    price_node = card.select_one(".price")
    if price_node:
        price_text = _clean_text(price_node.get_text(separator=" ", strip=True))
        if price_text:
            return price_text

    text = card.get_text(separator=" ", strip=True)
    match = PRICE_RE.search(text)
    return _clean_text(match.group(0)) if match else ""


def _shape_item(raw: dict[str, str], fields: list[str]) -> dict[str, str]:
    item: dict[str, str] = {}
    for field in ("title", "url", "price"):
        if _requested(fields, field) and raw.get(field):
            item[field] = raw[field]
    item["source"] = "scrapy"
    return item


def extract_items_from_html(html: str, base_url: str, fields: list[str]) -> list[dict[str, str]]:
    """Extract card-like records, falling back to links when no cards exist."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all(class_=lambda value: bool(value and CARD_CLASS_RE.search(str(value))))
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for card in cards:
        raw = {
            "title": _extract_title(card),
            "url": _extract_url(card, base_url),
            "price": _extract_price(card),
        }
        if not raw["title"] and not raw["url"]:
            continue
        key = (raw["title"], raw["url"])
        if key in seen:
            continue
        seen.add(key)
        items.append(_shape_item(raw, fields))

    if items:
        return items

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("javascript:") or href == "#":
            continue
        raw = {
            "title": _clean_text(anchor.get_text(separator=" ", strip=True)) or href,
            "url": urljoin(base_url, href),
            "price": "",
        }
        key = (raw["title"], raw["url"])
        if key in seen:
            continue
        seen.add(key)
        items.append(_shape_item(raw, fields))

    return items


SpiderBase = scrapy.Spider if scrapy is not None else object


class AutoScrapePaginationSpider(SpiderBase):
    name = "autoscrape_pagination"

    def __init__(
        self,
        start_url: str,
        fields: list[str],
        max_pages: int = DEFAULT_MAX_PAGES,
        max_items: int = DEFAULT_MAX_ITEMS,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        self.fields = fields
        self.max_pages = max_pages
        self.max_items = max_items
        self.allowed_domain = urlparse(start_url).netloc.lower()
        self.visited_urls: set[str] = set()
        self.pages_seen = 0
        self.items_seen = 0

    def parse(self, response: Any):
        status = getattr(response, "status", 200)
        if status in BLOCKED_STATUS_CODES:
            return

        current_url = response.url
        if current_url in self.visited_urls:
            return
        if self.pages_seen >= self.max_pages:
            return

        self.visited_urls.add(current_url)
        self.pages_seen += 1

        html = response.text
        for item in extract_items_from_html(html, current_url, self.fields):
            if self.items_seen >= self.max_items:
                return
            self.items_seen += 1
            yield item

        if self.pages_seen >= self.max_pages:
            return

        for next_url in find_next_page_candidates(
            html,
            current_url,
            allowed_domain=self.allowed_domain,
            visited_urls=self.visited_urls,
        ):
            if self.pages_seen >= self.max_pages:
                return
            if scrapy is None:
                yield {"next_url": next_url}
            else:
                yield scrapy.Request(next_url, callback=self.parse, dont_filter=True)


def run_scrapy_extractor(ctx: JobContext) -> JobContext:
    """
    Run the bounded Scrapy crawler and populate ctx.raw_items.

    Tests use the pure parsing helpers above to avoid reactor lifecycle issues.
    """
    if scrapy is None or CrawlerProcess is None or signals is None:
        warning = (
            "Scrapy extractor selected, but Scrapy is not installed. "
            "Install it with: pip install scrapy"
        )
        ctx.warnings.append(warning)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "scrapy_missing_dependency",
            "reason": warning,
        })
        return ctx

    max_pages = int(ctx.source_profile.get("max_pages", DEFAULT_MAX_PAGES))
    max_items = int(ctx.source_profile.get("max_items", DEFAULT_MAX_ITEMS))
    items: list[dict[str, str]] = []

    process = CrawlerProcess(settings={
        "USER_AGENT": USER_AGENT,
        "ROBOTSTXT_OBEY": True,
        "LOG_ENABLED": False,
        "DOWNLOAD_TIMEOUT": 10,
        "CLOSESPIDER_PAGECOUNT": max_pages,
        "CLOSESPIDER_ITEMCOUNT": max_items,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 0.25,
    })
    crawler = process.create_crawler(AutoScrapePaginationSpider)

    def _collect_item(item: dict[str, str], response: Any, spider: Any) -> None:
        if len(items) < max_items:
            items.append(dict(item))

    crawler.signals.connect(_collect_item, signal=signals.item_scraped)
    process.crawl(
        crawler,
        start_url=ctx.url,
        fields=ctx.fields,
        max_pages=max_pages,
        max_items=max_items,
    )
    process.start(stop_after_crawl=True)

    ctx.raw_items = items
    reason = (
        f"Extracted {len(items)} raw item(s) from paginated HTML using Scrapy "
        f"with max_pages={max_pages}, max_items={max_items}, same-domain pagination only."
    )
    ctx.decisions.append({
        "layer": "extractor",
        "decision": "extracted",
        "reason": reason,
    })
    return ctx
