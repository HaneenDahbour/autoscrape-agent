"""
main.py — CLI entry point for AutoScrape Agent.

Usage:
  python -m src.main --url https://example.com --fields title,url --outputs csv,sqlite

Arguments:
  --url      Target URL to scrape (required)
  --fields   Comma-separated list of fields to extract (required)
  --outputs  Comma-separated output formats: csv, sqlite (default: csv)
"""

import argparse
import json
import sys

from src.models import JobContext
from src.agent.orchestrator import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AutoScrape Agent — ethical, auditable web data extraction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m src.main --url https://example.com --fields title,url --outputs csv\n"
            "  python -m src.main --url https://books.toscrape.com --fields title,price,url --outputs csv,sqlite\n"
        ),
    )
    parser.add_argument("--url", required=True, help="Target URL to scrape.")
    parser.add_argument(
        "--fields",
        required=True,
        help="Comma-separated fields to extract (e.g. title,url,price).",
    )
    parser.add_argument(
        "--outputs",
        default="csv",
        help="Comma-separated output formats: csv, sqlite (default: csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    outputs = [o.strip() for o in args.outputs.split(",") if o.strip()]

    # Build the initial context from CLI inputs
    ctx = JobContext(
        url=args.url,
        fields=fields,
        outputs=outputs,
    )

    print(f"\n[AutoScrape Agent] Starting job for: {ctx.url}")
    print(f"  Fields  : {ctx.fields}")
    print(f"  Outputs : {ctx.outputs}\n")

    # Run the pipeline
    ctx = run_pipeline(ctx)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n── Pipeline Complete ─────────────────────────────────")
    print(f"  Risk level         : {ctx.risk_level}")
    print(f"  Allowed            : {ctx.allowed}")
    print(f"  Authorization      : {ctx.authorization_status}")
    print(f"  Strategy           : {ctx.selected_strategy}")
    if ctx.scrape_route:
        print(f"  Scrape route       : {ctx.scrape_route['route']} ({ctx.scrape_route['confidence']})")
    print(f"  Raw items          : {len(ctx.raw_items)}")
    print(f"  Valid items        : {len(ctx.valid_items)}")
    print(f"  Invalid items      : {len(ctx.invalid_items)}")
    print(f"  Duplicates removed : {ctx.duplicates_removed}")

    if ctx.warnings:
        print(f"\n  Warnings ({len(ctx.warnings)}):")
        for w in ctx.warnings:
            print(f"    ⚠  {w}")

    if ctx.errors:
        print(f"\n  Errors ({len(ctx.errors)}):")
        for e in ctx.errors:
            print(f"    ✗  {e}")

    if ctx.output_paths:
        print(f"\n  Output files:")
        for fmt, path in ctx.output_paths.items():
            print(f"    [{fmt}] {path}")

    if ctx.route_explanation:
        print(f"\n{ctx.route_explanation}")

    print("\n── Decisions audit trail ─────────────────────────────")
    for d in ctx.decisions:
        print(f"  [{d['layer']}] {d['decision']}: {d['reason'][:100]}")

    print()

    # Exit non-zero if the job was blocked or had errors
    if not ctx.allowed or ctx.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
