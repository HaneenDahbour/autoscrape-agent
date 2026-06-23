"""
Tests for src/processing/validator.py

Covers:
  - Valid item passes through
  - Missing title → invalid
  - Empty title → invalid
  - Missing url → invalid
  - url with non-http scheme → invalid
  - Non-numeric price → invalid
  - Numeric price passes
  - No price field is fine
  - Decision appended to ctx.decisions
"""

import pytest
from src.models import JobContext
from src.processing.validator import run_validator


def make_ctx(clean_items: list[dict]) -> JobContext:
    ctx = JobContext(url="https://example.com", fields=["title", "url"], outputs=["csv"])
    ctx.clean_items = clean_items
    return ctx


# ── Valid items ───────────────────────────────────────────────────────────────

def test_valid_item_passes():
    ctx = run_validator(make_ctx([{"title": "Hello", "url": "https://example.com"}]))
    assert len(ctx.valid_items) == 1
    assert len(ctx.invalid_items) == 0


def test_valid_item_with_price_passes():
    ctx = run_validator(make_ctx([
        {"title": "Book", "url": "https://example.com", "price": "12.99"}
    ]))
    assert len(ctx.valid_items) == 1


def test_valid_item_without_price_passes():
    ctx = run_validator(make_ctx([{"title": "Link", "url": "https://example.com/a"}]))
    assert len(ctx.valid_items) == 1


# ── Missing / empty title ─────────────────────────────────────────────────────

def test_missing_title_is_invalid():
    ctx = run_validator(make_ctx([{"url": "https://example.com"}]))
    assert len(ctx.invalid_items) == 1
    assert "title" in ctx.invalid_items[0]["_validation_error"]


def test_empty_title_is_invalid():
    ctx = run_validator(make_ctx([{"title": "", "url": "https://example.com"}]))
    assert len(ctx.invalid_items) == 1


def test_whitespace_only_title_is_invalid():
    ctx = run_validator(make_ctx([{"title": "   ", "url": "https://example.com"}]))
    assert len(ctx.invalid_items) == 1


# ── Missing / invalid URL ─────────────────────────────────────────────────────

def test_missing_url_is_invalid():
    ctx = run_validator(make_ctx([{"title": "Hello"}]))
    assert len(ctx.invalid_items) == 1
    assert "url" in ctx.invalid_items[0]["_validation_error"]


def test_ftp_url_is_invalid():
    ctx = run_validator(make_ctx([{"title": "Hello", "url": "ftp://example.com"}]))
    assert len(ctx.invalid_items) == 1


def test_relative_url_is_invalid():
    ctx = run_validator(make_ctx([{"title": "Hello", "url": "/about"}]))
    assert len(ctx.invalid_items) == 1


def test_http_url_is_valid():
    ctx = run_validator(make_ctx([{"title": "Hello", "url": "http://example.com"}]))
    assert len(ctx.valid_items) == 1


def test_https_url_is_valid():
    ctx = run_validator(make_ctx([{"title": "Hello", "url": "https://example.com"}]))
    assert len(ctx.valid_items) == 1


# ── Price validation ──────────────────────────────────────────────────────────

def test_non_numeric_price_is_invalid():
    ctx = run_validator(make_ctx([
        {"title": "Item", "url": "https://example.com", "price": "free"}
    ]))
    assert len(ctx.invalid_items) == 1
    assert "price" in ctx.invalid_items[0]["_validation_error"]


def test_numeric_string_price_is_valid():
    ctx = run_validator(make_ctx([
        {"title": "Item", "url": "https://example.com", "price": "9.99"}
    ]))
    assert len(ctx.valid_items) == 1


def test_none_price_is_valid():
    ctx = run_validator(make_ctx([
        {"title": "Item", "url": "https://example.com", "price": None}
    ]))
    assert len(ctx.valid_items) == 1


# ── Decision ──────────────────────────────────────────────────────────────────

def test_decision_appended():
    ctx = run_validator(make_ctx([{"title": "Hello", "url": "https://example.com"}]))
    decisions = [d for d in ctx.decisions if d["layer"] == "validator"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "validated"


# ── Mixed valid and invalid ───────────────────────────────────────────────────

def test_mixed_valid_and_invalid():
    items = [
        {"title": "Good", "url": "https://example.com"},
        {"url": "https://example.com/b"},            # missing title
        {"title": "Bad URL", "url": "not-a-url"},    # invalid url
        {"title": "OK", "url": "https://example.com/c"},
    ]
    ctx = run_validator(make_ctx(items))
    assert len(ctx.valid_items) == 2
    assert len(ctx.invalid_items) == 2
