"""
Tests for src/processing/cleaner.py

Covers:
  - Whitespace normalisation
  - Relative URL resolution to absolute
  - Price string cleaning
  - Empty raw_items skipped cleanly
  - Decision appended to ctx.decisions
"""

import pytest
from src.models import JobContext
from src.processing.cleaner import run_cleaner


def make_ctx(raw_items: list[dict], url: str = "https://example.com") -> JobContext:
    ctx = JobContext(url=url, fields=["title", "url"], outputs=["csv"])
    ctx.raw_items = raw_items
    return ctx


# ── Whitespace normalisation ──────────────────────────────────────────────────

def test_normalises_whitespace_in_title():
    ctx = run_cleaner(make_ctx([{"title": "  Hello   World  ", "url": "https://example.com/a"}]))
    assert ctx.clean_items[0]["title"] == "Hello World"


def test_normalises_whitespace_in_url():
    ctx = run_cleaner(make_ctx([{"title": "Test", "url": "  https://example.com/a  "}]))
    # After normalisation and urljoin, the URL should be clean
    assert "  " not in ctx.clean_items[0]["url"]


# ── Relative URL resolution ───────────────────────────────────────────────────

def test_resolves_relative_url():
    ctx = run_cleaner(make_ctx(
        [{"title": "Page", "url": "/about"}],
        url="https://example.com"
    ))
    assert ctx.clean_items[0]["url"] == "https://example.com/about"


def test_resolves_relative_url_with_path_base():
    ctx = run_cleaner(make_ctx(
        [{"title": "Sub", "url": "sub/page"}],
        url="https://example.com/section/"
    ))
    assert ctx.clean_items[0]["url"] == "https://example.com/section/sub/page"


def test_absolute_url_unchanged():
    ctx = run_cleaner(make_ctx(
        [{"title": "External", "url": "https://other.com/page"}],
        url="https://example.com"
    ))
    assert ctx.clean_items[0]["url"] == "https://other.com/page"


# ── Price cleaning ────────────────────────────────────────────────────────────

def test_cleans_price_with_currency_symbol():
    ctx = run_cleaner(make_ctx(
        [{"title": "Item", "url": "https://example.com", "price": "£12.99"}]
    ))
    assert ctx.clean_items[0]["price"] == "12.99"


def test_cleans_price_with_comma_separator():
    ctx = run_cleaner(make_ctx(
        [{"title": "Item", "url": "https://example.com", "price": "$1,299.00"}]
    ))
    assert ctx.clean_items[0]["price"] == "1299.00"


def test_invalid_price_becomes_none():
    ctx = run_cleaner(make_ctx(
        [{"title": "Item", "url": "https://example.com", "price": "N/A"}]
    ))
    assert ctx.clean_items[0]["price"] is None


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_raw_items_skipped():
    ctx = run_cleaner(make_ctx([]))
    assert ctx.clean_items == []
    decisions = [d for d in ctx.decisions if d["layer"] == "cleaner"]
    assert decisions[0]["decision"] == "skipped"


def test_decision_appended():
    ctx = run_cleaner(make_ctx([{"title": "T", "url": "https://example.com"}]))
    decisions = [d for d in ctx.decisions if d["layer"] == "cleaner"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "cleaned"
