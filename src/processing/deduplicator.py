"""
deduplicator.py — Remove duplicate items using URL as the deduplication key.

Logic:
  Keep the first occurrence of each URL.
  Count removed duplicates and store in ctx.duplicates_removed.

Input:  ctx.valid_items
Output: ctx.valid_items (deduplicated, in-place)
        ctx.duplicates_removed
"""

from src.models import JobContext


def run_deduplicator(ctx: JobContext) -> JobContext:
    """
    Deduplicate ctx.valid_items on the 'url' field.
    Appends a decision to ctx.decisions.
    """
    seen_urls: set[str] = set()
    unique_items = []

    for item in ctx.valid_items:
        url = item.get("url", "")
        if url not in seen_urls:
            seen_urls.add(url)
            unique_items.append(item)

    removed = len(ctx.valid_items) - len(unique_items)
    ctx.valid_items = unique_items
    ctx.duplicates_removed = removed

    ctx.decisions.append({
        "layer": "deduplicator",
        "decision": "deduplicated",
        "reason": (
            f"Removed {removed} duplicate(s) using 'url' as the key. "
            f"{len(unique_items)} unique item(s) remain."
        ),
    })
    return ctx
