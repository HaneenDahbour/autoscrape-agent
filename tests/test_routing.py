"""
Tests for src/routing.py.
"""

import pytest

from src.routing import decide_scrape_route, format_route_explanation


NORMAL_HTML = """
<html>
  <head><title>Catalog</title></head>
  <body>
    <h1>Products</h1>
    <article class="product-card">
      <a href="/products/widget">Widget Pro</a>
      <p>Reliable widget for teams. Price: $29.99. In stock today.</p>
    </article>
  </body>
</html>
"""

SCRIPT_HEAVY_HTML = (
    "<html><head>"
    + "<script>window.__DATA__ = {};</script>" * 8
    + "</head><body><div id='app'></div></body></html>"
)

BLOCKED_HTML = """
<html><body>
  <h1>Access denied</h1>
  <p>Please verify you are human before continuing. CAPTCHA required.</p>
</body></html>
"""

XML_CONTENT = """
<?xml version="1.0" encoding="UTF-8"?>
<items>
  <item>
    <title>Product A</title>
    <url>/products/a</url>
  </item>
</items>
"""


def test_json_url_routes_to_api_like_json():
    route = decide_scrape_route("https://example.com/data.json")

    assert route.route == "api_like_json"
    assert route.reasons


def test_json_content_routes_to_api_like_json():
    route = decide_scrape_route(
        "https://example.com/api",
        html='{"items": [{"title": "Widget"}]}',
    )

    assert route.route == "api_like_json"
    assert "Detected JSON-like content" in route.reasons


def test_xml_url_routes_to_api_like_xml():
    route = decide_scrape_route("https://example.com/products.xml")

    assert route.route == "api_like_xml"
    assert route.confidence == "green"
    assert "URL path ends with .xml/.rss/.atom" in route.reasons


def test_xml_metadata_routes_to_api_like_xml():
    route = decide_scrape_route(
        "https://example.com/feed",
        metadata={"is_xml": True},
    )

    assert route.route == "api_like_xml"
    assert route.confidence == "green"
    assert "Source profiler detected XML content" in route.reasons


def test_xml_like_content_routes_to_api_like_xml():
    route = decide_scrape_route("https://example.com/feed", html=XML_CONTENT)

    assert route.route == "api_like_xml"
    assert route.confidence == "green"
    assert "Detected XML-like content" in route.reasons


def test_xml_route_has_at_least_one_reason():
    route = decide_scrape_route("https://example.com/feed.atom")

    assert route.route == "api_like_xml"
    assert route.reasons


def test_normal_html_routes_to_static_html():
    route = decide_scrape_route("https://example.com/products", html=NORMAL_HTML)

    assert route.route == "static_html"
    assert "Static HTML appears sufficient" in route.reasons


def test_script_heavy_low_text_html_routes_to_browser_render():
    route = decide_scrape_route("https://example.com/app", html=SCRIPT_HEAVY_HTML)

    assert route.route == "browser_render"
    assert "HTML contains many script tags" in route.reasons
    assert "Visible text length is low" in route.reasons


def test_blocked_captcha_html_routes_to_fallback_manual_review():
    route = decide_scrape_route("https://example.com/blocked", html=BLOCKED_HTML)

    assert route.route == "fallback_manual_review"
    assert route.confidence == "red"
    assert any("blocked/captcha/access denied" in reason for reason in route.reasons)


@pytest.mark.parametrize(
    ("url", "html", "metadata"),
    [
        ("https://example.com/data.json", None, None),
        ("https://example.com/api", '{"ok": true}', None),
        ("https://example.com/products.xml", None, None),
        ("https://example.com/feed", XML_CONTENT, None),
        ("https://example.com/profiled.xml", None, {"is_xml": True}),
        ("https://example.com/products", NORMAL_HTML, None),
        ("https://example.com/app", SCRIPT_HEAVY_HTML, None),
        ("https://example.com/blocked", BLOCKED_HTML, None),
        ("https://example.com/profiled", None, {"data_visible_in_html": True, "is_html": True}),
    ],
)
def test_every_route_has_at_least_one_reason(url, html, metadata):
    route = decide_scrape_route(url, html=html, metadata=metadata)

    assert route.reasons


def test_format_route_explanation_includes_route_reasons_and_next_step():
    route = decide_scrape_route("https://example.com/products", html=NORMAL_HTML)
    explanation = format_route_explanation(route)

    assert "Scrape route: static_html" in explanation
    assert "Reasons:" in explanation
    assert "Recommended next step:" in explanation
