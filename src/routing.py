"""
routing.py - Explainable scrape-route selection.

The router is a lightweight, deterministic layer that explains what kind of
scraping approach appears appropriate for a URL/content pair. It does not fetch
pages or require browser automation. Browser rendering is currently a
recommendation route only; the V1 extractor pipeline still decides what can
actually run.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from dataclasses import asdict, dataclass
from typing import Any, Literal

from bs4 import BeautifulSoup

Confidence = Literal["green", "yellow", "red"]
RouteName = Literal[
    "static_html",
    "scrapy_crawl",
    "browser_render",
    "api_like_json",
    "api_like_xml",
    "fallback_manual_review",
]

SCRIPT_HEAVY_THRESHOLD = 6
LOW_VISIBLE_TEXT_THRESHOLD = 120
VERY_SHORT_HTML_THRESHOLD = 80

BLOCKED_PATTERNS = (
    "access denied",
    "captcha",
    "cf-challenge",
    "cloudflare ray id",
    "forbidden",
    "please enable cookies",
    "verify you are human",
    "unusual traffic",
    "too many requests",
)

XML_URL_EXTENSIONS = (".xml", ".rss", ".atom")
XML_START_PATTERNS = ("<?xml", "<rss", "<feed", "<items", "<products", "<entries")
SCRAPY_CRAWL_NEXT_STEP = (
    "Use bounded Scrapy crawling for paginated static HTML. Review crawl limits, "
    "extracted records, and the audit report before scaling beyond the local demo."
)
NEXT_TEXT_VALUES = {"next", ">", "\xbb", "التالي", "الصفحة التالية"}
PAGINATION_HREF_RE = re.compile(
    r"([?&]page=\d+|[?&]page=|/page/\d+\b|[?&]offset=|[?&]cursor=)",
    re.IGNORECASE,
)
PAGINATION_CLASS_RE = re.compile(r"(pagination|pager|next-page)", re.IGNORECASE)


@dataclass
class ScrapeRoute:
    route: RouteName
    confidence: Confidence
    reasons: list[str]
    signals: dict[str, Any]
    recommended_next_step: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _looks_like_json(content: str) -> bool:
    stripped = content.strip()
    if not stripped or stripped[0] not in "{[":
        return False

    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _looks_like_xml(content: str) -> bool:
    stripped = content.strip()
    lowered = stripped.lower()
    if not stripped or not stripped.startswith("<"):
        return False

    if lowered.startswith(XML_START_PATTERNS):
        return True

    if re.search(r"<(item|product|entry)\b[^>]*>.*</\1>", stripped, re.IGNORECASE | re.DOTALL):
        return True

    return False


def _url_path_ends_with(url: str, extensions: tuple[str, ...]) -> bool:
    return urlparse(url).path.lower().endswith(extensions)


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


def _detect_html_pagination(soup: BeautifulSoup) -> tuple[bool, list[str], int]:
    signals: list[str] = []
    candidate_anchor_ids = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = anchor.get_text(separator=" ", strip=True).lower()

        if _rel_contains_next(anchor.get("rel")):
            signals.append("a[rel=next]")
            candidate_anchor_ids.add(id(anchor))

        if text in NEXT_TEXT_VALUES:
            signals.append(f"next-like anchor text: {text}")
            candidate_anchor_ids.add(id(anchor))

        if PAGINATION_HREF_RE.search(href):
            signals.append("pagination href pattern")
            candidate_anchor_ids.add(id(anchor))

        if _class_or_id_contains_pagination(anchor):
            signals.append("pagination class/id on anchor")
            candidate_anchor_ids.add(id(anchor))

    if soup.find(_class_or_id_contains_pagination):
        signals.append("pagination class/id on element")

    pagination_signals = list(dict.fromkeys(signals))
    return bool(pagination_signals), pagination_signals, len(candidate_anchor_ids)


def _html_signals(html: str | None) -> dict[str, Any]:
    if html is None:
        return {
            "html_provided": False,
            "html_length": 0,
            "script_count": 0,
            "visible_text_length": 0,
            "target_like_structure_count": 0,
            "blocked_pattern": None,
            "json_like_content": False,
            "xml_like_content": False,
            "html_has_pagination": False,
            "html_pagination_signals": [],
            "html_next_page_candidates_count": 0,
        }

    lowered = html.lower()
    blocked_pattern = next(
        (pattern for pattern in BLOCKED_PATTERNS if pattern in lowered),
        None,
    )

    if _looks_like_json(html):
        return {
            "html_provided": True,
            "html_length": len(html),
            "script_count": 0,
            "visible_text_length": 0,
            "target_like_structure_count": 0,
            "blocked_pattern": blocked_pattern,
            "json_like_content": True,
            "xml_like_content": False,
            "html_has_pagination": False,
            "html_pagination_signals": [],
            "html_next_page_candidates_count": 0,
        }

    if _looks_like_xml(html):
        return {
            "html_provided": True,
            "html_length": len(html),
            "script_count": 0,
            "visible_text_length": 0,
            "target_like_structure_count": 0,
            "blocked_pattern": blocked_pattern,
            "json_like_content": False,
            "xml_like_content": True,
            "html_has_pagination": False,
            "html_pagination_signals": [],
            "html_next_page_candidates_count": 0,
        }

    soup = BeautifulSoup(html, "lxml")
    has_pagination, pagination_signals, next_page_candidates_count = _detect_html_pagination(soup)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    visible_text = soup.get_text(separator=" ", strip=True)
    structure_count = (
        len(soup.find_all(["article", "table", "ul", "ol", "h1", "h2", "h3"]))
        + len(soup.find_all("a", href=True))
        + len(soup.select("[class*=item], [class*=product], [class*=card], [class*=result]"))
    )

    return {
        "html_provided": True,
        "html_length": len(html),
        "script_count": len(re.findall(r"<script\b", html, flags=re.IGNORECASE)),
        "visible_text_length": len(visible_text),
        "target_like_structure_count": structure_count,
        "blocked_pattern": blocked_pattern,
        "json_like_content": False,
        "xml_like_content": False,
        "html_has_pagination": has_pagination,
        "html_pagination_signals": pagination_signals,
        "html_next_page_candidates_count": next_page_candidates_count,
    }


def _metadata_signals(metadata: dict | None) -> dict[str, Any]:
    metadata = metadata or {}
    return {
        "status_code": metadata.get("status_code"),
        "content_type": metadata.get("content_type", ""),
        "is_json": bool(metadata.get("is_json")),
        "is_xml": bool(metadata.get("is_xml")),
        "is_html": bool(metadata.get("is_html")),
        "js_heavy": bool(metadata.get("js_heavy")),
        "data_visible_in_html": bool(metadata.get("data_visible_in_html")),
        "has_pagination": bool(metadata.get("has_pagination") or metadata.get("pagination_detected")),
        "pagination_signals": metadata.get("pagination_signals", []),
        "next_page_candidates_count": metadata.get("next_page_candidates_count", 0),
        "visible_field_hits": metadata.get("visible_field_hits", []),
        "metadata_error": metadata.get("error"),
    }


def decide_scrape_route(
    url: str,
    html: str | None = None,
    metadata: dict | None = None,
) -> ScrapeRoute:
    """
    Choose an explainable scrape route from URL, optional content, and metadata.

    The rules are intentionally plain heuristics so the decision can be audited.
    """
    reasons: list[str] = []
    html_info = _html_signals(html)
    meta_info = _metadata_signals(metadata)
    signals = {
        "url": url,
        **html_info,
        **meta_info,
    }

    status_code = meta_info["status_code"]
    if status_code in (401, 403, 429):
        reasons.append(f"HTTP status {status_code} indicates access is blocked or rate limited")

    if meta_info["metadata_error"]:
        reasons.append("Source profiler reported an error")

    if html_info["blocked_pattern"]:
        reasons.append(f"Detected blocked/captcha/access denied pattern: {html_info['blocked_pattern']}")

    if reasons:
        return ScrapeRoute(
            route="fallback_manual_review",
            confidence="red",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Stop automatic extraction and inspect access, permissions, or anti-bot requirements manually.",
        )

    content_type = str(meta_info["content_type"]).lower()
    if (
        _url_path_ends_with(url, (".json",))
        or "json" in content_type
        or meta_info["is_json"]
        or html_info["json_like_content"]
    ):
        reasons.append("Detected JSON-like content")
        if _url_path_ends_with(url, (".json",)):
            reasons.append("URL path ends with .json")
        return ScrapeRoute(
            route="api_like_json",
            confidence="green",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Use a JSON/API parser when that extractor is available.",
        )

    if (
        _url_path_ends_with(url, XML_URL_EXTENSIONS)
        or "xml" in content_type
        or "rss" in content_type
        or "atom" in content_type
        or meta_info["is_xml"]
        or html_info["xml_like_content"]
    ):
        reasons.append("Detected XML-like content")
        if _url_path_ends_with(url, XML_URL_EXTENSIONS):
            reasons.append("URL path ends with .xml/.rss/.atom")
        if meta_info["is_xml"]:
            reasons.append("Source profiler detected XML content")
        return ScrapeRoute(
            route="api_like_xml",
            confidence="green",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Use the XML extractor through the api_xml strategy when available.",
        )

    if html is None:
        reasons.append("HTML content was not provided to the router")
        if meta_info["js_heavy"]:
            reasons.append("Profiler marked the page as JavaScript-heavy")
            return ScrapeRoute(
                route="browser_render",
                confidence="yellow",
                reasons=reasons,
                signals=signals,
                recommended_next_step="Recommend browser rendering, but keep V1 extraction unchanged until a browser extractor is installed.",
            )
        if meta_info["data_visible_in_html"] and meta_info["has_pagination"]:
            reasons.append("Profiler found visible target-like data in HTML")
            reasons.append("Profiler detected pagination, so this is a crawl case")
            return ScrapeRoute(
                route="scrapy_crawl",
                confidence="yellow",
                reasons=reasons,
                signals=signals,
                recommended_next_step=SCRAPY_CRAWL_NEXT_STEP,
            )
        if meta_info["data_visible_in_html"]:
            reasons.append("Profiler found visible target-like data in HTML")
            return ScrapeRoute(
                route="static_html",
                confidence="yellow",
                reasons=reasons,
                signals=signals,
                recommended_next_step="Use the existing static HTML extractor.",
            )
        return ScrapeRoute(
            route="fallback_manual_review",
            confidence="yellow",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Fetch and inspect the page content before choosing an extractor.",
        )

    if html_info["html_length"] < VERY_SHORT_HTML_THRESHOLD:
        reasons.append("HTML is missing or very short")
        return ScrapeRoute(
            route="browser_render",
            confidence="yellow",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Try browser rendering or inspect the response manually if the page remains empty.",
        )

    if (
        html_info["script_count"] >= SCRIPT_HEAVY_THRESHOLD
        and html_info["visible_text_length"] < LOW_VISIBLE_TEXT_THRESHOLD
    ):
        reasons.append("HTML contains many script tags")
        reasons.append("Visible text length is low")
        return ScrapeRoute(
            route="browser_render",
            confidence="yellow",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Recommend browser rendering; do not force it until Playwright/Selenium support exists.",
        )

    if (
        html_info["visible_text_length"] >= LOW_VISIBLE_TEXT_THRESHOLD
        or html_info["target_like_structure_count"] > 0
        or meta_info["data_visible_in_html"]
    ):
        has_pagination = html_info["html_has_pagination"] or meta_info["has_pagination"]
        if has_pagination:
            reasons.append("Static HTML contains visible target-like data")
            reasons.append("Pagination was detected, so this is a crawl case")
            return ScrapeRoute(
                route="scrapy_crawl",
                confidence="green",
                reasons=reasons,
                signals=signals,
                recommended_next_step=SCRAPY_CRAWL_NEXT_STEP,
            )

        reasons.append("Static HTML appears sufficient")
        if html_info["target_like_structure_count"] > 0:
            reasons.append("HTML contains target-like structure")
        return ScrapeRoute(
            route="static_html",
            confidence="green",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Use the existing static HTML extractor.",
        )

    reasons.append("No reliable automatic route matched the available signals")
    return ScrapeRoute(
        route="fallback_manual_review",
        confidence="red",
        reasons=reasons,
        signals=signals,
        recommended_next_step="Inspect the page manually and add a source-specific extractor only if appropriate.",
    )


def format_route_explanation(route: ScrapeRoute) -> str:
    """Return a compact human-readable explanation for a ScrapeRoute."""
    reason_lines = "\n".join(f"  - {reason}" for reason in route.reasons)
    return (
        f"Scrape route: {route.route} ({route.confidence})\n"
        f"Reasons:\n{reason_lines}\n"
        f"Recommended next step: {route.recommended_next_step}"
    )
