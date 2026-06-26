"""
orchestrator.py — Wire all pipeline layers in sequence.

Pipeline order:
  1. Risk Engine       — block sensitive fields
  2. Robots Checker    — respect robots.txt
  3. Source Profiler   — probe the URL
  4. Strategy Selector — pick extraction method
  5. Extractor         — extract raw items (strategy-dependent)
  6. Cleaner           — normalise data
  7. Validator         — enforce field rules
  8. Deduplicator      — remove duplicate URLs
  9. Storage           — write CSV and/or SQLite
  10. Report Generator  — write run_report.json

Each layer receives JobContext, mutates it, and returns it.
If a layer sets ctx.allowed=False, the orchestrator short-circuits
everything up to and including storage, but still writes the report.
"""

from src.models import JobContext
from src.policy.risk_engine import run_risk_engine
from src.policy.robots_checker import run_robots_checker
from src.profiler.source_profiler import run_source_profiler
from src.agent.strategy_selector import run_strategy_selector
from src.routing import decide_scrape_route, format_route_explanation
from src.extractors.registry import get_extractor
from src.processing.cleaner import run_cleaner
from src.processing.validator import run_validator
from src.processing.deduplicator import run_deduplicator
from src.storage.csv_exporter import run_csv_exporter
from src.storage.sqlite_store import run_sqlite_store
from src.reporting.run_report import run_report_generator


def run_pipeline(ctx: JobContext) -> JobContext:
    """
    Execute the full AutoScrape pipeline for a given JobContext.
    Returns the final JobContext with all fields populated.
    """

    # ── 1. Risk engine ───────────────────────────────────────────────────────
    ctx = run_risk_engine(ctx)

    # ── 2. Robots checker ────────────────────────────────────────────────────
    ctx = run_robots_checker(ctx)

    # ── 3. Source profiler ───────────────────────────────────────────────────
    ctx = run_source_profiler(ctx)

    # ── 4. Strategy selector ─────────────────────────────────────────────────
    ctx = run_strategy_selector(ctx)

    # Step 3. Explainable routing records the recommended scrape route without
    # replacing the V1 strategy selector or extractor registry.
    route = decide_scrape_route(ctx.url, metadata=ctx.source_profile)
    ctx.scrape_route = route.to_dict()
    ctx.route_explanation = format_route_explanation(route)
    ctx.decisions.append({
        "layer": "routing",
        "decision": route.route,
        "reason": "; ".join(route.reasons),
    })

    # ── 5. Extractor (only if job is still allowed) ──────────────────────────
    if ctx.allowed and ctx.selected_strategy not in ("blocked", "unknown"):
        extractor = get_extractor(ctx.selected_strategy)
        if extractor:
            ctx = extractor(ctx)
        else:
            ctx.warnings.append(
                f"No extractor registered for strategy '{ctx.selected_strategy}'."
            )

    # ── 6. Cleaner ───────────────────────────────────────────────────────────
    ctx = run_cleaner(ctx)

    # ── 7. Validator ─────────────────────────────────────────────────────────
    ctx = run_validator(ctx)

    # ── 8. Deduplicator ──────────────────────────────────────────────────────
    ctx = run_deduplicator(ctx)

    # ── 9. Storage (only requested outputs) ──────────────────────────────────
    if "csv" in ctx.outputs:
        ctx = run_csv_exporter(ctx)
    if "sqlite" in ctx.outputs:
        ctx = run_sqlite_store(ctx)

    # ── 10. Report (always) ──────────────────────────────────────────────────
    ctx = run_report_generator(ctx)

    return ctx
