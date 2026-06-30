"""
models.py — Core data contract for AutoScrape Agent.

JobContext is passed through every pipeline layer.
Each layer reads what it needs, mutates relevant fields, and returns the same object.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobContext:
    # ── Input ────────────────────────────────────────────────────────────────
    url: str                          # Target URL supplied by the user
    fields: list[str]                 # Fields the user wants to extract
    outputs: list[str]                # Output formats requested (csv, sqlite)

    # ── Policy ───────────────────────────────────────────────────────────────
    risk_level: str = "unknown"       # "low", "high", or "unknown"
    allowed: bool = True              # False if blocked by risk engine or robots
    authorization_status: str = "unknown"
    # "permitted"  — risk engine + robots both green
    # "blocked"    — risk engine or robots said no
    # "warning"    — robots.txt could not be read, continuing with caution
    # "unknown"    — not yet evaluated

    # ── Profiler ─────────────────────────────────────────────────────────────
    source_profile: dict[str, Any] = field(default_factory=dict)
    # Keys set by source_profiler:
    #   status_code, content_type, html_size,
    #   is_json, is_xml, is_html,
    #   js_heavy, has_pagination, pagination_detected,
    #   pagination_signals, next_page_candidates_count,
    #   data_visible_in_html

    # ── Strategy ─────────────────────────────────────────────────────────────
    selected_strategy: str = "unknown"
    # "blocked", "api_json", "api_xml", "scrapy",
    # "static_html", "selenium", "manual_review", "unknown"
    strategy_reason: str = ""
    scrape_route: dict[str, Any] = field(default_factory=dict)
    route_explanation: str = ""

    # ── Extracted data ───────────────────────────────────────────────────────
    raw_items: list[dict[str, Any]] = field(default_factory=list)
    clean_items: list[dict[str, Any]] = field(default_factory=list)
    valid_items: list[dict[str, Any]] = field(default_factory=list)
    invalid_items: list[dict[str, Any]] = field(default_factory=list)
    duplicates_removed: int = 0

    # ── Audit trail ──────────────────────────────────────────────────────────
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    decisions: list[dict[str, str]] = field(default_factory=list)
    # Each decision: {"layer": str, "decision": str, "reason": str}

    # ── Outputs ──────────────────────────────────────────────────────────────
    output_paths: dict[str, str] = field(default_factory=dict)
    # e.g. {"csv": "data/exports/run_20240101.csv", "sqlite": "data/exports/data.db"}
