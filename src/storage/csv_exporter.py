"""
csv_exporter.py — Export valid items to a CSV file.

Output path: data/exports/run_<timestamp>.csv
"""

import csv
import os
from datetime import datetime
from src.models import JobContext

EXPORTS_DIR = os.path.join("data", "exports")


def run_csv_exporter(ctx: JobContext) -> JobContext:
    """
    Write ctx.valid_items to a CSV file.
    Sets ctx.output_paths["csv"].
    Appends a decision to ctx.decisions.
    """
    if not ctx.valid_items:
        ctx.decisions.append({
            "layer": "csv_exporter",
            "decision": "skipped",
            "reason": "No valid items to export.",
        })
        return ctx

    os.makedirs(EXPORTS_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORTS_DIR, f"run_{timestamp}.csv")

    # Collect all field names across items (order: title, url, then the rest)
    all_keys: list[str] = []
    for item in ctx.valid_items:
        for k in item:
            if k not in all_keys:
                all_keys.append(k)

    # Ensure title and url come first if present
    priority = [k for k in ("title", "url", "source") if k in all_keys]
    rest = [k for k in all_keys if k not in priority]
    fieldnames = priority + rest

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ctx.valid_items)

    ctx.output_paths["csv"] = path
    ctx.decisions.append({
        "layer": "csv_exporter",
        "decision": "exported",
        "reason": f"Wrote {len(ctx.valid_items)} item(s) to CSV: {path}",
    })
    return ctx
