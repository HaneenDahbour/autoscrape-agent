"""
Tests for src/agent/strategy_selector.py

Covers:
  - blocked when ctx.allowed is False
  - api_json when source is JSON
  - api_xml when source is XML
  - static_html when HTML + data visible + no pagination + not JS-heavy
  - scrapy when HTML + data visible + pagination
  - selenium when HTML + JS-heavy
  - manual_review as fallback
  - Decision is always appended to ctx.decisions
"""

import pytest
from src.models import JobContext
from src.agent.strategy_selector import run_strategy_selector


def make_ctx(allowed: bool = True, profile: dict = None) -> JobContext:
    ctx = JobContext(url="https://example.com", fields=["title", "url"], outputs=["csv"])
    ctx.allowed = allowed
    ctx.source_profile = profile or {}
    return ctx


def html_profile(**kwargs) -> dict:
    base = {
        "is_html": True, "is_json": False, "is_xml": False,
        "js_heavy": False, "pagination_detected": False, "data_visible_in_html": True,
    }
    base.update(kwargs)
    return base


# ── Blocked ───────────────────────────────────────────────────────────────────

def test_blocked_when_not_allowed():
    ctx = run_strategy_selector(make_ctx(allowed=False))
    assert ctx.selected_strategy == "blocked"


def test_blocked_decision_appended():
    ctx = run_strategy_selector(make_ctx(allowed=False))
    decisions = [d for d in ctx.decisions if d["layer"] == "strategy_selector"]
    assert decisions[0]["decision"] == "blocked"


# ── JSON ──────────────────────────────────────────────────────────────────────

def test_chooses_api_json():
    profile = {"is_json": True, "is_xml": False, "is_html": False,
               "js_heavy": False, "pagination_detected": False, "data_visible_in_html": False}
    ctx = run_strategy_selector(make_ctx(profile=profile))
    assert ctx.selected_strategy == "api_json"


# ── XML ───────────────────────────────────────────────────────────────────────

def test_chooses_api_xml():
    profile = {"is_json": False, "is_xml": True, "is_html": False,
               "js_heavy": False, "pagination_detected": False, "data_visible_in_html": False}
    ctx = run_strategy_selector(make_ctx(profile=profile))
    assert ctx.selected_strategy == "api_xml"


# ── Static HTML ───────────────────────────────────────────────────────────────

def test_chooses_static_html():
    ctx = run_strategy_selector(make_ctx(profile=html_profile()))
    assert ctx.selected_strategy == "static_html"


def test_static_html_decision_appended():
    ctx = run_strategy_selector(make_ctx(profile=html_profile()))
    decisions = [d for d in ctx.decisions if d["layer"] == "strategy_selector"]
    assert decisions[0]["decision"] == "static_html"


# ── Scrapy ────────────────────────────────────────────────────────────────────

def test_chooses_scrapy_when_paginated():
    ctx = run_strategy_selector(
        make_ctx(profile=html_profile(pagination_detected=True))
    )
    assert ctx.selected_strategy == "scrapy"


# ── Selenium ──────────────────────────────────────────────────────────────────

def test_chooses_selenium_when_js_heavy():
    ctx = run_strategy_selector(
        make_ctx(profile=html_profile(js_heavy=True, data_visible_in_html=False))
    )
    assert ctx.selected_strategy == "selenium"


# ── Manual review ─────────────────────────────────────────────────────────────

def test_chooses_manual_review_as_fallback():
    """Empty profile matches no rule → manual_review."""
    ctx = run_strategy_selector(make_ctx(profile={}))
    assert ctx.selected_strategy == "manual_review"


# ── Strategy reason populated ─────────────────────────────────────────────────

def test_strategy_reason_is_set():
    ctx = run_strategy_selector(make_ctx(profile=html_profile()))
    assert ctx.strategy_reason != ""
