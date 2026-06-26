"""
Tests for src/extractors/xml_extractor.py.
"""

from unittest.mock import MagicMock, patch

from src.extractors.xml_extractor import extract_xml_items, run_xml_extractor
from src.models import JobContext


def mock_response(text, status=200):
    response = MagicMock()
    response.status_code = status
    response.text = text
    return response


def make_ctx(fields=None):
    return JobContext(
        url="https://example.com/api/products.xml",
        fields=fields or ["title", "url", "price"],
        outputs=["csv"],
    )


def test_items_item_extracts_correctly():
    xml = """
    <items>
      <item>
        <title>Product A</title>
        <url>/products/a</url>
        <price>10 JOD</price>
      </item>
      <item>
        <title>Product B</title>
        <url>/products/b</url>
        <price>12 JOD</price>
      </item>
    </items>
    """

    with patch("src.extractors.xml_extractor.requests.get", return_value=mock_response(xml)):
        items = extract_xml_items("https://example.com/api/products.xml", ["title", "url"])

    assert items == [
        {"title": "Product A", "url": "/products/a", "source": "api_xml"},
        {"title": "Product B", "url": "/products/b", "source": "api_xml"},
    ]


def test_products_product_extracts_correctly():
    xml = """
    <products>
      <product>
        <title>Widget</title>
        <url>/products/widget</url>
        <price>9.99</price>
      </product>
    </products>
    """

    with patch("src.extractors.xml_extractor.requests.get", return_value=mock_response(xml)):
        items = extract_xml_items("https://example.com/api/products.xml", ["title", "price"])

    assert items == [{"title": "Widget", "price": "9.99", "source": "api_xml"}]


def test_feed_entry_extracts_correctly():
    xml = """
    <feed>
      <entry>
        <title>Post One</title>
        <url>/posts/one</url>
      </entry>
    </feed>
    """

    with patch("src.extractors.xml_extractor.requests.get", return_value=mock_response(xml)):
        items = extract_xml_items("https://example.com/feed.xml", ["title", "url"])

    assert items == [{"title": "Post One", "url": "/posts/one", "source": "api_xml"}]


def test_repeated_root_children_fallback_extracts_correctly():
    xml = """
    <catalog>
      <record>
        <title>Fallback A</title>
        <url>/a</url>
      </record>
      <record>
        <title>Fallback B</title>
        <url>/b</url>
      </record>
    </catalog>
    """

    with patch("src.extractors.xml_extractor.requests.get", return_value=mock_response(xml)):
        items = extract_xml_items("https://example.com/catalog.xml", ["title", "url"])

    assert items == [
        {"title": "Fallback A", "url": "/a", "source": "api_xml"},
        {"title": "Fallback B", "url": "/b", "source": "api_xml"},
    ]


def test_invalid_xml_is_handled_safely():
    ctx = make_ctx()

    with patch(
        "src.extractors.xml_extractor.requests.get",
        return_value=mock_response("<items><item><title>Broken</items>"),
    ):
        ctx = run_xml_extractor(ctx)

    assert ctx.raw_items == []
    assert ctx.warnings
    assert ctx.decisions[-1]["decision"] == "xml_parse_failed"


def test_requested_fields_are_respected():
    xml = """
    <items>
      <item>
        <title>Product A</title>
        <url>/products/a</url>
        <price>10 JOD</price>
      </item>
    </items>
    """

    with patch("src.extractors.xml_extractor.requests.get", return_value=mock_response(xml)):
        items = extract_xml_items("https://example.com/api/products.xml", ["title"])

    assert items == [{"title": "Product A", "source": "api_xml"}]


def test_source_field_is_added():
    xml = """
    <items>
      <item><title>Product A</title></item>
    </items>
    """

    with patch("src.extractors.xml_extractor.requests.get", return_value=mock_response(xml)):
        items = extract_xml_items("https://example.com/api/products.xml", ["title"])

    assert items[0]["source"] == "api_xml"


def test_blocked_status_is_handled_safely():
    ctx = make_ctx()

    with patch(
        "src.extractors.xml_extractor.requests.get",
        return_value=mock_response("<items></items>", status=403),
    ):
        ctx = run_xml_extractor(ctx)

    assert ctx.raw_items == []
    assert ctx.decisions[-1]["decision"] == "xml_blocked_status"
