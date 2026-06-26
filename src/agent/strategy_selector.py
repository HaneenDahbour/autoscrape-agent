"""
strategy_selector.py — Rule-based extraction strategy selection.

Purpose:
  Inspect ctx.allowed and ctx.source_profile and apply a fixed decision tree
  to pick the right extraction strategy. This is entirely deterministic —
  no ML or heuristics.

Strategy options:
  blocked       — job not permitted to proceed
  api_json      — response is JSON (V2 implemented)
  api_xml       — response is XML (V2 planned)
  scrapy        — HTML with visible data and pagination (V3 planned)
  static_html   — HTML with visible data, no pagination (V1 IMPLEMENTED)
  selenium      — HTML but JavaScript-rendered content (V3 planned)
  manual_review — none of the above matched

Static HTML and API-like JSON have real extractors. Other strategies log a
clear decision and skip extraction with a note that they are planned for V2/V3.
"""

from src.models import JobContext


def run_strategy_selector(ctx: JobContext) -> JobContext:
    """
    Select an extraction strategy based on ctx.allowed and ctx.source_profile.

    Sets:
      ctx.selected_strategy
      ctx.strategy_reason
    Appends a decision to ctx.decisions.
    """
    # ── Blocked ──────────────────────────────────────────────────────────────
    if not ctx.allowed:
        ctx.selected_strategy = "blocked"
        ctx.strategy_reason = (
            "Job was blocked by an earlier layer (risk engine or robots checker). "
            "No extraction will take place."
        )
        ctx.decisions.append({
            "layer": "strategy_selector",
            "decision": "blocked",
            "reason": ctx.strategy_reason,
        })
        return ctx

    p = ctx.source_profile

    # ── JSON API ─────────────────────────────────────────────────────────────
    if p.get("is_json"):
        ctx.selected_strategy = "api_json"
        ctx.strategy_reason = (
            "Response Content-Type is JSON. "
            "API-like JSON extraction is available and should be used by the extractor registry."
        )
        ctx.decisions.append({
            "layer": "strategy_selector",
            "decision": "api_json",
            "reason": ctx.strategy_reason,
        })
        return ctx

    # ── XML API ──────────────────────────────────────────────────────────────
    if p.get("is_xml"):
        ctx.selected_strategy = "api_xml"
        ctx.strategy_reason = (
            "Response Content-Type is XML. "
            "XML extractor is planned for V2; skipping extraction."
        )
        ctx.decisions.append({
            "layer": "strategy_selector",
            "decision": "api_xml",
            "reason": ctx.strategy_reason,
        })
        return ctx

    # ── HTML strategies ───────────────────────────────────────────────────────
    if p.get("is_html"):

        # Paginated HTML with visible data → Scrapy (multi-page crawl)
        if p.get("data_visible_in_html") and p.get("pagination_detected"):
            ctx.selected_strategy = "scrapy"
            ctx.strategy_reason = (
                "HTML page has visible data and pagination links. "
                "Multi-page Scrapy crawl is planned for V3; skipping extraction."
            )
            ctx.decisions.append({
                "layer": "strategy_selector",
                "decision": "scrapy",
                "reason": ctx.strategy_reason,
            })
            return ctx

        # Single-page HTML with visible data → static_html (V1 implemented)
        if p.get("data_visible_in_html") and not p.get("js_heavy"):
            ctx.selected_strategy = "static_html"
            ctx.strategy_reason = (
                "HTML page has visible data and no JavaScript-rendering required. "
                "Using static HTML extractor (requests + BeautifulSoup)."
            )
            ctx.decisions.append({
                "layer": "strategy_selector",
                "decision": "static_html",
                "reason": ctx.strategy_reason,
            })
            return ctx

        # JavaScript-heavy → Selenium needed
        if p.get("js_heavy"):
            ctx.selected_strategy = "selenium"
            ctx.strategy_reason = (
                "Page appears to be JavaScript-rendered (many scripts, little "
                "visible text). Selenium extractor is planned for V3; skipping."
            )
            ctx.decisions.append({
                "layer": "strategy_selector",
                "decision": "selenium",
                "reason": ctx.strategy_reason,
            })
            return ctx

    # ── Fallback ─────────────────────────────────────────────────────────────
    ctx.selected_strategy = "manual_review"
    ctx.strategy_reason = (
        "No automatic strategy matched the source profile. "
        "Manual inspection required."
    )
    ctx.decisions.append({
        "layer": "strategy_selector",
        "decision": "manual_review",
        "reason": ctx.strategy_reason,
    })
    return ctx
