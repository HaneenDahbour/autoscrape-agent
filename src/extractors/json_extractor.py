"""
json_extractor.py - Extract records from API-like JSON responses.

Strategy: api_json / api_like_json
Implemented: V2

Supported shapes:
  - list[object]
  - {"items": list[object]}
  - {"products": list[object]}
  - {"data": list[object]}
  - nested {"data": {"items": list[object]}}-style payloads

The extractor does not bypass access controls. It makes one normal HTTP GET,
stops on blocked status codes, and returns no items on invalid JSON.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from src.models import JobContext

USER_AGENT = "AutoScrapeAgent/1.0"
REQUEST_TIMEOUT = 10
BLOCKED_STATUS_CODES = {401, 403, 429}
CONTAINER_KEYS = ("items", "products", "data")
URL_ALIASES = ("url", "href", "link", "path")


def _find_records(payload: Any) -> list[dict[str, Any]]:
    """Return the first list of objects found in a common API payload shape."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in CONTAINER_KEYS:
        value = payload.get(key)
        records = _find_records(value)
        if records:
            return records

    for value in payload.values():
        if isinstance(value, (dict, list)):
            records = _find_records(value)
            if records:
                return records

    return []


def _normalise_record(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Keep requested fields that exist, add URL aliases, and stamp source."""
    item: dict[str, Any] = {}

    for field in fields:
        if field in record:
            item[field] = record[field]
            continue

        if field == "url":
            for alias in URL_ALIASES:
                if alias in record:
                    item["url"] = record[alias]
                    break

    item["source"] = "api_like_json"
    return item


def extract_json_items(url: str, fields: list[str]) -> list[dict]:
    """
    Fetch a URL, parse JSON safely, and return normalised item dictionaries.

    Safe failures return an empty list. The pipeline wrapper records the
    matching warning/error decision for auditability.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException:
        return []

    if response.status_code in BLOCKED_STATUS_CODES:
        return []

    try:
        payload = response.json()
    except ValueError:
        try:
            payload = json.loads(response.text)
        except (TypeError, json.JSONDecodeError):
            return []

    records = _find_records(payload)
    return [_normalise_record(record, fields) for record in records]


def run_json_extractor(ctx: JobContext) -> JobContext:
    """
    Extract raw items from an API-like JSON response.

    Populates ctx.raw_items and appends an extractor decision. Safe failures do
    not crash the pipeline.
    """
    try:
        response = requests.get(
            ctx.url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        warning = f"json_extractor: network error fetching {ctx.url}: {exc}"
        ctx.warnings.append(warning)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "json_fetch_failed",
            "reason": warning,
        })
        return ctx

    if response.status_code in BLOCKED_STATUS_CODES:
        warning = (
            f"json_extractor: HTTP {response.status_code} indicates the endpoint "
            "is blocked, private, or rate limited. No extraction attempted."
        )
        ctx.warnings.append(warning)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "json_blocked_status",
            "reason": warning,
        })
        return ctx

    try:
        payload = response.json()
    except ValueError:
        try:
            payload = json.loads(response.text)
        except (TypeError, json.JSONDecodeError) as exc:
            warning = f"json_extractor: invalid JSON from {ctx.url}: {exc}"
            ctx.warnings.append(warning)
            ctx.decisions.append({
                "layer": "extractor",
                "decision": "json_parse_failed",
                "reason": warning,
            })
            return ctx

    records = _find_records(payload)
    ctx.raw_items = [_normalise_record(record, ctx.fields) for record in records]

    reason = (
        f"Extracted {len(ctx.raw_items)} raw item(s) from {ctx.url} "
        "using API-like JSON extraction."
    )
    ctx.decisions.append({
        "layer": "extractor",
        "decision": "json_extracted",
        "reason": reason,
    })
    return ctx
