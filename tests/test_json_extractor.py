"""
Tests for src/extractors/json_extractor.py.
"""

from unittest.mock import MagicMock, patch

from src.extractors.json_extractor import extract_json_items, run_json_extractor
from src.models import JobContext
from src.routing import decide_scrape_route


def mock_response(payload=None, text="", status=200, json_error=None):
    response = MagicMock()
    response.status_code = status
    response.text = text
    if json_error:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload
    return response


def make_ctx(fields=None):
    return JobContext(
        url="https://example.com/api/products.json",
        fields=fields or ["title", "url", "price"],
        outputs=["csv"],
    )


def test_json_list_routes_and_extracts_correctly():
    payload = [
        {"title": "Widget", "url": "/products/widget", "price": "$10", "extra": "ignored"},
        {"title": "Gadget", "url": "/products/gadget", "price": "$12"},
    ]

    route = decide_scrape_route("https://example.com/products.json")
    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/products.json", ["title", "url"])

    assert route.route == "api_like_json"
    assert items == [
        {"title": "Widget", "url": "/products/widget", "source": "api_like_json"},
        {"title": "Gadget", "url": "/products/gadget", "source": "api_like_json"},
    ]


def test_items_container_extracts_correctly():
    payload = {"items": [{"title": "Item One", "url": "/one"}]}

    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/api", ["title", "url"])

    assert items == [{"title": "Item One", "url": "/one", "source": "api_like_json"}]


def test_products_container_extracts_correctly():
    payload = {"products": [{"title": "Product One", "path": "/p/one"}]}

    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/api", ["title", "url"])

    assert items == [{"title": "Product One", "url": "/p/one", "source": "api_like_json"}]


def test_data_container_extracts_correctly():
    payload = {"data": [{"title": "Data Item", "link": "/data/item"}]}

    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/api", ["title", "url"])

    assert items == [{"title": "Data Item", "url": "/data/item", "source": "api_like_json"}]


def test_nested_data_list_extracts_correctly():
    payload = {"data": {"items": [{"title": "Nested", "href": "/nested"}]}}

    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/api", ["title", "url"])

    assert items == [{"title": "Nested", "url": "/nested", "source": "api_like_json"}]


def test_invalid_json_is_handled_safely():
    ctx = make_ctx()

    with patch(
        "src.extractors.json_extractor.requests.get",
        return_value=mock_response(text="<html>not json</html>", json_error=ValueError("bad json")),
    ):
        ctx = run_json_extractor(ctx)

    assert ctx.raw_items == []
    assert ctx.warnings
    assert ctx.decisions[-1]["decision"] == "json_parse_failed"


def test_requested_fields_are_respected():
    payload = [{"title": "Widget", "url": "/products/widget", "price": "$10", "stock": 5}]

    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/api", ["title"])

    assert items == [{"title": "Widget", "source": "api_like_json"}]


def test_source_field_is_added():
    payload = {"items": [{"title": "Widget"}]}

    with patch("src.extractors.json_extractor.requests.get", return_value=mock_response(payload)):
        items = extract_json_items("https://example.com/api", ["title"])

    assert items[0]["source"] == "api_like_json"


def test_blocked_status_is_handled_safely():
    ctx = make_ctx()

    with patch(
        "src.extractors.json_extractor.requests.get",
        return_value=mock_response(status=403, payload={"items": [{"title": "Nope"}]}),
    ):
        ctx = run_json_extractor(ctx)

    assert ctx.raw_items == []
    assert ctx.decisions[-1]["decision"] == "json_blocked_status"
