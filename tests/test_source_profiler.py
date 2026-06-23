"""
Tests for src/profiler/source_profiler.py

All tests mock requests.get so no real HTTP calls are made.

Covers:
  - "title" field: detected via soup.title
  - "title" field: detected via h1/h2 heading tags
  - "title" field: detected via link text when no <title> tag
  - "url" field: detected when a[href] links exist
  - "url" field: NOT detected when no links
  - "price" field: detected via currency+number pattern
  - "price" field: NOT detected when no price pattern
  - "availability" field: detected via availability keywords
  - Generic field fallback: field name found in body text
  - Generic field fallback: NOT detected when field name absent
  - data_visible_in_html = True when any field has a hit
  - data_visible_in_html = False when no field has evidence
  - example.com-like minimal HTML -> data_visible_in_html=True for title+url
  - Blocking status codes (401, 403, 429) still block regardless
  - New profile keys are present: visible_field_hits, link_count,
    title_candidates_count, price_candidates_count
  - Job already blocked -> skipped
  - Network error -> blocked
  - JS-heavy detection still works
  - Pagination detection still works
"""

import pytest
import requests as _requests
from unittest.mock import MagicMock, patch
from src.models import JobContext
from src.profiler.source_profiler import run_source_profiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(fields, url="https://example.com"):
    return JobContext(url=url, fields=fields, outputs=["csv"])


def mock_response(html, status=200, content_type="text/html"):
    """Build a fake requests.Response for a given HTML string."""
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"Content-Type": content_type}
    resp.text = html
    resp.content = html.encode("utf-8")
    return resp


MINIMAL_HTML = """
<html>
  <head><title>Example Domain</title></head>
  <body>
    <h1>Example Domain</h1>
    <p>This domain is for use in illustrative examples.</p>
    <a href="https://www.iana.org/domains/reserved">More information...</a>
  </body>
</html>
"""

PRICE_HTML = """
<html><head><title>Shop</title></head><body>
  <h1>Widget Pro</h1>
  <p class="price">$29.99</p>
  <a href="/cart">Add to cart</a>
</body></html>
"""

AVAILABILITY_HTML = """
<html><head><title>Store</title></head><body>
  <p>Status: In Stock</p>
  <a href="/buy">Buy now</a>
</body></html>
"""

NO_LINKS_HTML = """
<html><head><title>Static Page</title></head><body>
  <h1>Hello</h1><p>No links here.</p>
</body></html>
"""

JS_HEAVY_HTML = (
    "<html><head>"
    + "<script>var x=1;</script>" * 10
    + "</head><body><p>Hi</p></body></html>"
)

PAGINATED_HTML = """
<html><head><title>List</title></head><body>
  <ul><li><a href="/item/1">Item 1</a></li></ul>
  <div class="pagination"><a href="/page/2">Next</a></div>
</body></html>
"""


# ---------------------------------------------------------------------------
# Skipped when already blocked
# ---------------------------------------------------------------------------

def test_skips_when_already_blocked():
    ctx = make_ctx(["title"])
    ctx.allowed = False
    ctx = run_source_profiler(ctx)
    decisions = [d for d in ctx.decisions if d["layer"] == "source_profiler"]
    assert decisions[0]["decision"] == "skipped"


# ---------------------------------------------------------------------------
# Network error
# ---------------------------------------------------------------------------

def test_network_error_blocks_job():
    ctx = make_ctx(["title"])
    # Must raise a requests.exceptions.RequestException -- that's what the profiler catches
    with patch("src.profiler.source_profiler.requests.get",
               side_effect=_requests.exceptions.ConnectionError("timeout")):
        ctx = run_source_profiler(ctx)
    assert ctx.allowed is False
    assert len(ctx.errors) > 0
    decisions = [d for d in ctx.decisions if d["layer"] == "source_profiler"]
    assert decisions[0]["decision"] == "blocked"


# ---------------------------------------------------------------------------
# Blocking status codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [401, 403, 429])
def test_blocking_status_codes(status):
    ctx = make_ctx(["title", "url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response("", status=status)):
        ctx = run_source_profiler(ctx)
    assert ctx.allowed is False
    assert ctx.source_profile["data_visible_in_html"] is False
    decisions = [d for d in ctx.decisions if d["layer"] == "source_profiler"]
    assert decisions[0]["decision"] == "blocked"


# ---------------------------------------------------------------------------
# "title" field evidence
# ---------------------------------------------------------------------------

def test_title_detected_via_soup_title():
    ctx = make_ctx(["title"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(MINIMAL_HTML)):
        ctx = run_source_profiler(ctx)
    assert "title" in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["data_visible_in_html"] is True


def test_title_detected_via_h1():
    html = "<html><body><h1>Main Heading</h1></body></html>"
    ctx = make_ctx(["title"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "title" in ctx.source_profile["visible_field_hits"]


def test_title_detected_via_link_text():
    html = '<html><body><a href="/page">Click here</a></body></html>'
    ctx = make_ctx(["title"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "title" in ctx.source_profile["visible_field_hits"]


def test_title_not_detected_when_no_evidence():
    # No <title>, no headings, no links with text
    html = "<html><body><p>Some text.</p></body></html>"
    ctx = make_ctx(["title"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "title" not in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["data_visible_in_html"] is False


# ---------------------------------------------------------------------------
# "url" field evidence
# ---------------------------------------------------------------------------

def test_url_detected_when_links_exist():
    ctx = make_ctx(["url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(MINIMAL_HTML)):
        ctx = run_source_profiler(ctx)
    assert "url" in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["link_count"] >= 1


def test_url_not_detected_when_no_links():
    ctx = make_ctx(["url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(NO_LINKS_HTML)):
        ctx = run_source_profiler(ctx)
    assert "url" not in ctx.source_profile["visible_field_hits"]


# ---------------------------------------------------------------------------
# "price" field evidence
# ---------------------------------------------------------------------------

def test_price_detected_with_dollar_sign():
    ctx = make_ctx(["price"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(PRICE_HTML)):
        ctx = run_source_profiler(ctx)
    assert "price" in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["price_candidates_count"] >= 1


def test_price_detected_with_currency_code():
    html = "<html><body><p>Price: 25.00 JOD</p></body></html>"
    ctx = make_ctx(["price"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "price" in ctx.source_profile["visible_field_hits"]


def test_price_not_detected_when_no_pattern():
    html = "<html><body><h1>Product</h1><p>Description only.</p></body></html>"
    ctx = make_ctx(["price"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "price" not in ctx.source_profile["visible_field_hits"]


# ---------------------------------------------------------------------------
# "availability" field evidence
# ---------------------------------------------------------------------------

def test_availability_detected():
    ctx = make_ctx(["availability"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(AVAILABILITY_HTML)):
        ctx = run_source_profiler(ctx)
    assert "availability" in ctx.source_profile["visible_field_hits"]


def test_availability_detected_out_of_stock():
    html = "<html><body><p>Out of Stock</p></body></html>"
    ctx = make_ctx(["availability"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "availability" in ctx.source_profile["visible_field_hits"]


def test_availability_not_detected_when_absent():
    html = "<html><body><h1>Product</h1></body></html>"
    ctx = make_ctx(["availability"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "availability" not in ctx.source_profile["visible_field_hits"]


# ---------------------------------------------------------------------------
# Generic field fallback
# ---------------------------------------------------------------------------

def test_generic_field_detected_when_name_in_text():
    html = "<html><body><p>author: Jane Doe</p></body></html>"
    ctx = make_ctx(["author"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "author" in ctx.source_profile["visible_field_hits"]


def test_generic_field_not_detected_when_absent():
    html = "<html><body><p>Nothing relevant here.</p></body></html>"
    ctx = make_ctx(["author"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(html)):
        ctx = run_source_profiler(ctx)
    assert "author" not in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["data_visible_in_html"] is False


# ---------------------------------------------------------------------------
# example.com simulation (the original bug)
# ---------------------------------------------------------------------------

def test_example_com_like_page_is_visible_for_title_and_url():
    """
    example.com has a <title>, one <h1>, and one <a href>.
    With fields=[title, url], both should have evidence
    -> data_visible_in_html=True -> strategy becomes static_html.
    """
    ctx = make_ctx(["title", "url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(MINIMAL_HTML)):
        ctx = run_source_profiler(ctx)

    assert ctx.source_profile["is_html"] is True
    assert ctx.source_profile["data_visible_in_html"] is True
    assert "title" in ctx.source_profile["visible_field_hits"]
    assert "url" in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["link_count"] >= 1
    assert ctx.source_profile["title_candidates_count"] >= 1


# ---------------------------------------------------------------------------
# Strategy integration: example.com -> static_html
# ---------------------------------------------------------------------------

def test_example_com_profile_leads_to_static_html_strategy():
    """End-to-end: profiler output -> strategy_selector -> static_html."""
    from src.agent.strategy_selector import run_strategy_selector
    ctx = make_ctx(["title", "url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(MINIMAL_HTML)):
        ctx = run_source_profiler(ctx)
    ctx = run_strategy_selector(ctx)
    assert ctx.selected_strategy == "static_html"


# ---------------------------------------------------------------------------
# New profile keys always present
# ---------------------------------------------------------------------------

def test_new_profile_keys_present_on_success():
    ctx = make_ctx(["title", "url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(MINIMAL_HTML)):
        ctx = run_source_profiler(ctx)
    for key in ("visible_field_hits", "link_count",
                "title_candidates_count", "price_candidates_count"):
        assert key in ctx.source_profile, f"Missing key: {key}"


def test_new_profile_keys_present_on_blocked_status():
    ctx = make_ctx(["title"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response("", status=403)):
        ctx = run_source_profiler(ctx)
    for key in ("visible_field_hits", "link_count",
                "title_candidates_count", "price_candidates_count"):
        assert key in ctx.source_profile, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# JS-heavy and pagination still work
# ---------------------------------------------------------------------------

def test_js_heavy_detection_still_works():
    ctx = make_ctx(["title"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(JS_HEAVY_HTML)):
        ctx = run_source_profiler(ctx)
    assert ctx.source_profile["js_heavy"] is True


def test_pagination_detection_still_works():
    ctx = make_ctx(["title", "url"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(PAGINATED_HTML)):
        ctx = run_source_profiler(ctx)
    assert ctx.source_profile["pagination_detected"] is True


# ---------------------------------------------------------------------------
# Partial field hits
# ---------------------------------------------------------------------------

def test_partial_field_hits_still_set_data_visible_true():
    """title has evidence, price does not - data_visible_in_html should still be True."""
    ctx = make_ctx(["title", "price"])
    with patch("src.profiler.source_profiler.requests.get",
               return_value=mock_response(NO_LINKS_HTML)):
        ctx = run_source_profiler(ctx)
    # NO_LINKS_HTML has <title> tag -> title hit
    # NO_LINKS_HTML has no price pattern -> no price hit
    assert "title" in ctx.source_profile["visible_field_hits"]
    assert "price" not in ctx.source_profile["visible_field_hits"]
    assert ctx.source_profile["data_visible_in_html"] is True
