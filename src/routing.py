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
from dataclasses import asdict, dataclass
from typing import Any, Literal

from bs4 import BeautifulSoup

Confidence = Literal["green", "yellow", "red"]
RouteName = Literal[
    "static_html",
    "browser_render",
    "api_like_json",
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
        }

    soup = BeautifulSoup(html, "lxml")
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
    }


def _metadata_signals(metadata: dict | None) -> dict[str, Any]:
    metadata = metadata or {}
    return {
        "status_code": metadata.get("status_code"),
        "content_type": metadata.get("content_type", ""),
        "is_json": bool(metadata.get("is_json")),
        "is_html": bool(metadata.get("is_html")),
        "js_heavy": bool(metadata.get("js_heavy")),
        "data_visible_in_html": bool(metadata.get("data_visible_in_html")),
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
        url.lower().split("?", 1)[0].endswith(".json")
        or "json" in content_type
        or meta_info["is_json"]
        or html_info["json_like_content"]
    ):
        reasons.append("Detected JSON-like content")
        if url.lower().split("?", 1)[0].endswith(".json"):
            reasons.append("URL path ends with .json")
        return ScrapeRoute(
            route="api_like_json",
            confidence="green",
            reasons=reasons,
            signals=signals,
            recommended_next_step="Use a JSON/API parser when that extractor is available.",
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
