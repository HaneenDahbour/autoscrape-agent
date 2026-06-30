"""
Tests for src/extractors/scrapy_extractor.py.

These tests avoid starting the Scrapy engine so they do not depend on live
websites or Twisted reactor state.
"""

from unittest.mock import patch

from src.extractors.registry import get_extractor
from src.extractors.scrapy_extractor import (
    AutoScrapePaginationSpider,
    extract_items_from_html,
    find_next_page_candidates,
    run_scrapy_extractor,
)
from src.models import JobContext


PRODUCT_LIST_HTML = """
<html>
  <body>
    <article class="product-card">
      <h2>Widget Pro</h2>
      <a href="/products/widget">View</a>
      <p class="price">$29.99</p>
    </article>
    <div class="listing item">
      <a href="/products/gadget">Gadget</a>
      <span>Price: 15 JOD</span>
    </div>
  </body>
</html>
"""

PAGINATED_HTML = """
<html>
  <body>
    <a rel="next" href="/products?page=2">More</a>
    <a href="https://other.example/products?page=2">next</a>
    <a href="/about">About</a>
  </body>
</html>
"""


class FakeResponse:
    def __init__(self, url, text, status=200):
        self.url = url
        self.text = text
        self.status = status


def make_ctx():
    return JobContext(
        url="https://shop.example/products",
        fields=["title", "url", "price"],
        outputs=["csv"],
    )


def test_scrapy_extractor_extracts_product_cards_from_html():
    items = extract_items_from_html(
        PRODUCT_LIST_HTML,
        "https://shop.example/products",
        ["title", "url", "price"],
    )

    assert items == [
        {
            "title": "Widget Pro",
            "url": "https://shop.example/products/widget",
            "price": "$29.99",
            "source": "scrapy",
        },
        {
            "title": "Gadget",
            "url": "https://shop.example/products/gadget",
            "price": "15 JOD",
            "source": "scrapy",
        },
    ]


def test_scrapy_extractor_falls_back_to_links_when_no_cards_exist():
    html = '<html><body><a href="/one">One</a><a href="/two">Two</a></body></html>'

    items = extract_items_from_html(html, "https://shop.example/products", ["title", "url"])

    assert items == [
        {"title": "One", "url": "https://shop.example/one", "source": "scrapy"},
        {"title": "Two", "url": "https://shop.example/two", "source": "scrapy"},
    ]


def test_scrapy_extractor_finds_same_domain_next_page_candidates_only():
    candidates = find_next_page_candidates(
        PAGINATED_HTML,
        "https://shop.example/products",
        visited_urls=set(),
    )

    assert candidates == ["https://shop.example/products?page=2"]


def test_scrapy_extractor_skips_visited_next_page_candidates():
    candidates = find_next_page_candidates(
        PAGINATED_HTML,
        "https://shop.example/products",
        visited_urls={"https://shop.example/products?page=2"},
    )

    assert candidates == []


def test_scrapy_spider_respects_visited_url_logic():
    spider = AutoScrapePaginationSpider(
        start_url="https://shop.example/products",
        fields=["title", "url", "price"],
        max_pages=5,
        max_items=100,
    )
    response = FakeResponse("https://shop.example/products", PRODUCT_LIST_HTML)

    first_parse_items = list(spider.parse(response))
    second_parse_items = list(spider.parse(response))

    assert len(first_parse_items) == 2
    assert second_parse_items == []


def test_scrapy_spider_respects_max_pages_before_parsing():
    spider = AutoScrapePaginationSpider(
        start_url="https://shop.example/products",
        fields=["title", "url", "price"],
        max_pages=0,
        max_items=100,
    )
    response = FakeResponse("https://shop.example/products", PRODUCT_LIST_HTML)

    assert list(spider.parse(response)) == []


def test_registry_calls_scrapy_extractor_when_strategy_is_scrapy():
    ctx = make_ctx()
    ctx.selected_strategy = "scrapy"
    extractor = get_extractor(ctx.selected_strategy)

    with patch("src.extractors.scrapy_extractor.scrapy", None), \
         patch("src.extractors.scrapy_extractor.CrawlerProcess", None), \
         patch("src.extractors.scrapy_extractor.signals", None):
        result = extractor(ctx)

    assert result is ctx
    assert ctx.decisions[-1]["decision"] == "scrapy_missing_dependency"


def test_scrapy_extractor_reports_missing_dependency_safely():
    ctx = make_ctx()

    with patch("src.extractors.scrapy_extractor.scrapy", None), \
         patch("src.extractors.scrapy_extractor.CrawlerProcess", None), \
         patch("src.extractors.scrapy_extractor.signals", None):
        ctx = run_scrapy_extractor(ctx)

    assert ctx.raw_items == []
    assert ctx.warnings
    assert ctx.decisions[-1]["decision"] == "scrapy_missing_dependency"
