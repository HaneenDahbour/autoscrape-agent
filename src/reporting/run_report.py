"""
run_report.py — Write a structured JSON report of the pipeline run.

Output: data/exports/run_report.json

The report captures every key metric and the full audit trail (decisions list),
making the run reproducible and reviewable.
"""

import json
import os
from datetime import datetime, timezone
from src.models import JobContext

EXPORTS_DIR = os.path.join("data", "exports")
REPORT_PATH = os.path.join(EXPORTS_DIR, "run_report.json")


def run_report_generator(ctx: JobContext) -> JobContext:
    """
    Serialise the JobContext into a JSON report file.
    Sets ctx.output_paths["report"].
    Appends a decision to ctx.decisions.
    """
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),

        # ── Input ─────────────────────────────────────────────────────────
        "url": ctx.url,
        "fields": ctx.fields,
        "outputs": ctx.outputs,

        # ── Policy ────────────────────────────────────────────────────────
        "risk_level": ctx.risk_level,
        "allowed": ctx.allowed,
        "authorization_status": ctx.authorization_status,

        # ── Profiler ──────────────────────────────────────────────────────
        "source_profile": ctx.source_profile,

        # ── Strategy ──────────────────────────────────────────────────────
        "selected_strategy": ctx.selected_strategy,
        "strategy_reason": ctx.strategy_reason,

        # ── Extraction metrics ────────────────────────────────────────────
        "raw_items_count": len(ctx.raw_items),
        "clean_items_count": len(ctx.clean_items),
        "valid_items_count": len(ctx.valid_items),
        "invalid_items_count": len(ctx.invalid_items),
        "duplicates_removed": ctx.duplicates_removed,

        # ── Audit trail ───────────────────────────────────────────────────
        "warnings": ctx.warnings,
        "errors": ctx.errors,
        "decisions": ctx.decisions,

        # ── Output paths ──────────────────────────────────────────────────
        "output_paths": ctx.output_paths,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    ctx.output_paths["report"] = REPORT_PATH
    ctx.decisions.append({
        "layer": "report_generator",
        "decision": "reported",
        "reason": f"Run report written to {REPORT_PATH}.",
    })
    return ctx
