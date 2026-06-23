"""
cleaner.py — Normalise raw extracted items.

Operations:
  1. Strip and normalise whitespace in all string fields.
  2. Resolve relative URLs to absolute using the base URL from ctx.url.
  3. Clean price strings: remove currency symbols, commas; convert to float str.

Input:  ctx.raw_items
Output: ctx.clean_items
"""

import re
from urllib.parse import urljoin
from src.models import JobContext

# Matches currency symbols and thousands separators to strip from prices
PRICE_STRIP_RE = re.compile(r"[£$€¥,\s]")


def _normalise_whitespace(value: str) -> str:
    """Collapse all whitespace runs to a single space and strip ends."""
    return re.sub(r"\s+", " ", value).strip()


def _clean_price(price_str: str) -> str | None:
    """
    Remove currency symbols and commas, return a numeric string or None.
    Example: "£1,299.99" → "1299.99"
    """
    cleaned = PRICE_STRIP_RE.sub("", price_str)
    try:
        float(cleaned)   # validate it's actually a number
        return cleaned
    except ValueError:
        return None


def _clean_item(item: dict, base_url: str) -> dict:
    """Clean a single item dict."""
    result = {}
    for key, value in item.items():
        if not isinstance(value, str):
            result[key] = value
            continue

        # Normalise whitespace for all string fields
        value = _normalise_whitespace(value)

        # Resolve relative URLs
        if key in ("url", "href", "link"):
            value = urljoin(base_url, value)

        # Clean price strings
        if key == "price" and value:
            value = _clean_price(value)

        result[key] = value
    return result


def run_cleaner(ctx: JobContext) -> JobContext:
    """
    Clean all raw items and populate ctx.clean_items.
    Appends a decision to ctx.decisions.
    """
    if not ctx.raw_items:
        ctx.clean_items = []
        ctx.decisions.append({
            "layer": "cleaner",
            "decision": "skipped",
            "reason": "No raw items to clean.",
        })
        return ctx

    ctx.clean_items = [_clean_item(item, ctx.url) for item in ctx.raw_items]

    ctx.decisions.append({
        "layer": "cleaner",
        "decision": "cleaned",
        "reason": (
            f"Cleaned {len(ctx.clean_items)} item(s): normalised whitespace, "
            f"resolved relative URLs against '{ctx.url}', cleaned price strings."
        ),
    })
    return ctx
