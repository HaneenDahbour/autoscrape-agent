"""
validator.py — Enforce field-level data quality rules.

Rules:
  1. title must be present and non-empty.
  2. url must be present and start with http:// or https://.
  3. price, if present, must be a numeric string or None.

Items failing any rule are moved to ctx.invalid_items.
Valid items go to ctx.valid_items.

Input:  ctx.clean_items
Output: ctx.valid_items, ctx.invalid_items
"""

from src.models import JobContext


def _validate_item(item: dict) -> tuple[bool, str]:
    """
    Validate a single item.
    Returns (is_valid: bool, reason: str).
    """
    # Rule 1: title required
    title = item.get("title", "")
    if not title or not str(title).strip():
        return False, "Missing or empty 'title' field."

    # Rule 2: url must be present and have http/https scheme
    url = item.get("url", "")
    if not url:
        return False, "Missing 'url' field."
    if not (str(url).startswith("http://") or str(url).startswith("https://")):
        return False, f"Invalid URL scheme (must be http or https): '{url}'."

    # Rule 3: price must be numeric if present
    price = item.get("price")
    if price is not None:
        try:
            float(str(price))
        except (ValueError, TypeError):
            return False, f"'price' field is not numeric: '{price}'."

    return True, "ok"


def run_validator(ctx: JobContext) -> JobContext:
    """
    Validate all clean items.
    Populates ctx.valid_items and ctx.invalid_items.
    Appends a decision to ctx.decisions.
    """
    valid = []
    invalid = []

    for item in ctx.clean_items:
        is_valid, reason = _validate_item(item)
        if is_valid:
            valid.append(item)
        else:
            invalid_record = dict(item)
            invalid_record["_validation_error"] = reason
            invalid.append(invalid_record)

    ctx.valid_items = valid
    ctx.invalid_items = invalid

    ctx.decisions.append({
        "layer": "validator",
        "decision": "validated",
        "reason": (
            f"{len(valid)} item(s) valid, {len(invalid)} item(s) invalid. "
            f"Rules: title required, url must be http/https, price must be numeric."
        ),
    })
    return ctx
