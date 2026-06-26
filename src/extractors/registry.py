"""
registry.py — Maps strategy names to extractor functions.

Adding a new extractor in V2/V3:
  1. Import the function here.
  2. Add an entry to EXTRACTOR_REGISTRY.
  3. The orchestrator will pick it up automatically.
"""

from src.models import JobContext
from src.extractors.static_html_extractor import run_static_html_extractor
from src.extractors.json_extractor import run_json_extractor


def _not_implemented_extractor(strategy_name: str, version_note: str):
    """
    Returns a placeholder extractor for strategies not yet implemented.
    Logs a clear decision and returns ctx unchanged.
    """
    def _extractor(ctx: JobContext) -> JobContext:
        note = (
            f"Strategy '{strategy_name}' was selected but its extractor "
            f"is not implemented in V1. {version_note} No items extracted."
        )
        ctx.warnings.append(note)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": f"{strategy_name}_skipped",
            "reason": note,
        })
        return ctx
    return _extractor


# Maps strategy name → extractor callable(ctx) -> ctx
EXTRACTOR_REGISTRY: dict = {
    "static_html": run_static_html_extractor,
    "api_json": run_json_extractor,
    "api_like_json": run_json_extractor,

    # ── Planned for V2 ───────────────────────────────────────────────────────
    "api_xml": _not_implemented_extractor(
        "api_xml", "XML extractor planned for V2."
    ),

    # ── Planned for V3 ───────────────────────────────────────────────────────
    "scrapy": _not_implemented_extractor(
        "scrapy", "Multi-page Scrapy crawl planned for V3."
    ),
    "selenium": _not_implemented_extractor(
        "selenium", "JavaScript-rendering via Selenium planned for V3."
    ),
    "manual_review": _not_implemented_extractor(
        "manual_review", "No automatic extractor available; manual review required."
    ),
}


def get_extractor(strategy: str):
    """Return the extractor function for a given strategy name."""
    return EXTRACTOR_REGISTRY.get(strategy)
