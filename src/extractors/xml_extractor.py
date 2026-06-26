"""
xml_extractor.py - Extract records from API-like XML responses.

Strategy: api_xml
Implemented: V2.1

Supported shapes:
  - repeated <item> nodes
  - repeated <product> nodes
  - repeated <entry> nodes
  - fallback repeated child nodes under the root when they look record-like

The extractor does not bypass access controls. It makes one normal HTTP GET,
stops on blocked status codes, and returns no items on invalid XML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from src.models import JobContext

USER_AGENT = "AutoScrapeAgent/1.0"
REQUEST_TIMEOUT = 10
BLOCKED_STATUS_CODES = {401, 403, 429}
RECORD_TAGS = ("item", "product", "entry")


def _local_name(tag: str) -> str:
    """Strip XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1].lower()


def _node_to_dict(node: ET.Element) -> dict[str, str]:
    """Convert direct child tags of a record node into a flat dictionary."""
    item: dict[str, str] = {}

    for child in list(node):
        key = _local_name(child.tag)
        value = "".join(child.itertext()).strip()
        if key and value:
            item[key] = value

    if not item:
        text = "".join(node.itertext()).strip()
        if text:
            item[_local_name(node.tag)] = text

    return item


def _looks_record_like(node: ET.Element) -> bool:
    """Return True when a root child has at least one simple child value."""
    return any("".join(child.itertext()).strip() for child in list(node))


def _find_record_nodes(root: ET.Element) -> list[ET.Element]:
    """Find record nodes in common XML collection shapes."""
    for record_tag in RECORD_TAGS:
        nodes = [
            node for node in root.iter()
            if _local_name(node.tag) == record_tag and list(node)
        ]
        if nodes:
            return nodes

    root_children = list(root)
    child_tags = [_local_name(child.tag) for child in root_children]
    repeated_tags = {
        tag for tag in child_tags
        if child_tags.count(tag) > 1
    }

    return [
        child for child in root_children
        if _local_name(child.tag) in repeated_tags and _looks_record_like(child)
    ]


def _normalise_record(record: dict[str, str], fields: list[str]) -> dict[str, str]:
    """Keep requested fields that exist and stamp source."""
    item = {
        field: record[field]
        for field in fields
        if field in record
    }
    item["source"] = "api_xml"
    return item


def extract_xml_items(url: str, fields: list[str]) -> list[dict]:
    """
    Fetch a URL, parse XML safely, and return normalised item dictionaries.

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
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []

    records = [_node_to_dict(node) for node in _find_record_nodes(root)]
    return [_normalise_record(record, fields) for record in records]


def run_xml_extractor(ctx: JobContext) -> JobContext:
    """
    Extract raw items from an API-like XML response.

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
        warning = f"xml_extractor: network error fetching {ctx.url}: {exc}"
        ctx.warnings.append(warning)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "xml_fetch_failed",
            "reason": warning,
        })
        return ctx

    if response.status_code in BLOCKED_STATUS_CODES:
        warning = (
            f"xml_extractor: HTTP {response.status_code} indicates the endpoint "
            "is blocked, private, or rate limited. No extraction attempted."
        )
        ctx.warnings.append(warning)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "xml_blocked_status",
            "reason": warning,
        })
        return ctx

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        warning = f"xml_extractor: invalid XML from {ctx.url}: {exc}"
        ctx.warnings.append(warning)
        ctx.decisions.append({
            "layer": "extractor",
            "decision": "xml_parse_failed",
            "reason": warning,
        })
        return ctx

    records = [_node_to_dict(node) for node in _find_record_nodes(root)]
    ctx.raw_items = [_normalise_record(record, ctx.fields) for record in records]

    reason = (
        f"Extracted {len(ctx.raw_items)} raw item(s) from {ctx.url} "
        "using XML extraction."
    )
    ctx.decisions.append({
        "layer": "extractor",
        "decision": "xml_extracted",
        "reason": reason,
    })
    return ctx
