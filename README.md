# AutoScrape Agent

AutoScrape Agent is a Python portfolio project that demonstrates an interpretable and ethical web data extraction pipeline.

The goal is not to build a black-box scraper. The goal is to show how a scraping/data acquisition system can make safe, auditable decisions before extracting and storing data.

## Version 1 Status

Version 1 implements the core pipeline foundation:

1. CLI input
2. Risk engine
3. Robots.txt checker
4. Source profiler
5. Strategy selector
6. Extractor registry
7. Static HTML extractor
8. Cleaner
9. Validator
10. Deduplicator
11. CSV exporter
12. SQLite storage
13. JSON run report
14. Unit tests

## Why This Project Exists

Companies often need structured data from public websites or APIs. The difficult part is not only extracting HTML. A professional data extraction system should:

* check whether the request is safe,
* inspect the source before choosing a tool,
* choose the simplest reliable extraction strategy,
* clean messy extracted data,
* validate records before storage,
* remove duplicates,
* store results,
* and generate an audit report explaining every decision.

## Architecture

The pipeline uses a shared `JobContext` object. Each layer receives the context, updates it, and appends a decision with a reason.

Flow:

```text
CLI Request
   ↓
JobContext
   ↓
Risk Engine
   ↓
Robots Checker
   ↓
Source Profiler
   ↓
Strategy Selector
   ↓
Extractor Registry
   ↓
Extractor
   ↓
Cleaner
   ↓
Validator
   ↓
Deduplicator
   ↓
Storage
   ↓
Run Report
```

## V1 Strategy Selector

The strategy selector chooses the extraction approach using deterministic rules:

```text
If blocked by risk or authorization → blocked
If response is JSON → api_json
If response is XML → api_xml
If HTML has visible data and pagination → scrapy
If HTML has visible data → static_html
If HTML appears JavaScript-heavy → selenium
Otherwise → manual_review
```

In V1, only the `static_html` extractor is implemented. Other strategies are intentionally marked as planned future work.

## Step 3 — Explainable Routing

Step 3 adds an explainable routing layer before extraction. The router inspects the URL, optional HTML/content, and profiler metadata, then records a `ScrapeRoute` with:

* the recommended route,
* a green/yellow/red confidence label,
* human-readable reasons,
* the signals used for the decision,
* and the recommended next step.

Supported routes:

* `static_html` - normal HTML appears sufficient for extraction.
* `browser_render` - the page looks JavaScript-heavy or too empty for static parsing. This is currently a recommendation only; Playwright/Selenium is not forced.
* `api_like_json` - the URL, content type, profiler metadata, or content looks JSON-like.
* `fallback_manual_review` - blocked/captcha/access denied patterns or unclear signals require manual inspection.

Explainability matters because scraping decisions should be auditable. Instead of silently choosing a tool, the pipeline now records why it selected a route, what evidence it used, and what should happen next.

Run the tests with:

```powershell
python -m pytest
```

## V2 — API-like JSON Extraction

V2 adds a JSON extractor for API-like endpoints. When a site exposes structured JSON, that path is preferred because it is usually cleaner, less brittle, and more respectful than parsing rendered HTML.

Supported JSON shapes:

* a top-level list of objects,
* an object with `items`,
* an object with `products`,
* an object with `data`,
* nested containers such as `{"data": {"items": [...]}}`.

This fits the explainable routing layer directly: when the existing strategy selector chooses `api_json`, or the Step 3 router recommends `api_like_json`, the pipeline uses the JSON extractor. Static HTML extraction remains unchanged, and browser rendering is still only a recommendation route.

The JSON extractor keeps requested fields when present, maps common URL-like fields such as `path`, `href`, or `link` into `url` when requested, stamps each record with `source = "api_like_json"`, and lets the existing cleaner resolve relative URLs. Invalid JSON, blocked status codes, and network failures are handled safely with warnings/decisions instead of crashing the pipeline.

Run the tests with:

```powershell
python -m pytest
```

## V2.1 — XML Extraction

XML still matters because many feeds, catalogs, government datasets, sitemaps, legacy APIs, and publishing systems expose structured data as XML instead of JSON. When XML is available, AutoScrape Agent can use it as a structured source rather than scraping rendered HTML.

Supported XML shapes:

* repeated `<item>` nodes,
* repeated `<product>` nodes,
* repeated `<entry>` nodes,
* fallback repeated child nodes under the root when they look like records.

This fits the existing strategy selector and extractor registry directly: when the source profiler marks a response as XML, the strategy selector chooses `api_xml`, and the extractor registry now maps `api_xml` to the XML extractor. Explainable routing also detects XML sources as `api_like_xml` from URL extensions, metadata, or XML-like content. JSON and static HTML behavior are unchanged.

The XML extractor keeps requested simple child tags when present, stamps each item with `source = "api_xml"`, and lets the existing cleaner handle relative URLs. Invalid XML, blocked status codes, and network failures are handled safely with warnings/decisions instead of crashing the pipeline.

Run the tests with:

```powershell
python -m pytest
```

## Safety Rules

AutoScrape Agent V1 does not:

* bypass CAPTCHA,
* bypass login walls,
* evade anti-bot systems,
* scrape private account data,
* collect sensitive personal data,
* continue after 401, 403, or 429 responses.

If the system cannot confidently choose a safe strategy, it falls back to `manual_review`.

## Current Test Result

The current V1 test suite passes:

```text
54 passed
```

Tested layers include:

* risk engine,
* strategy selector,
* cleaner,
* validator.

## Example Run

```powershell
python -m src.main --url https://example.com --fields title,url --outputs csv,sqlite
```

Example result:

```text
Risk level   : low
Allowed      : True
Authorization: permitted
Strategy     : manual_review
Report       : data/exports/run_report.json
```

The first integration run safely selected `manual_review` because the profiler did not yet have enough evidence to choose `static_html` for `example.com`. This is expected conservative behavior for V1 and will be improved in the next stage by making the profiler detect candidate HTML elements more intelligently.

## What I Learned

This project helped me understand the real workflow behind web data extraction:

* how to inspect a web source before scraping,
* how to choose between API, static HTML, Scrapy, Selenium, blocked, or manual review,
* why data cleaning and validation matter,
* how to make scraping safer and more ethical,
* and how to make an agent auditable instead of black-box.

## Next Stages

### V1.1 — Improve Source Profiler

Improve `data_visible_in_html` detection by checking candidate HTML elements such as:

* page title,
* h1/h2 headings,
* links,
* price-like text,
* availability words.

### V2 — API Ingestion

Add:

* JSON API extractor,
* XML parser,
* API pagination handling.

### V3 — Crawling and Dynamic Pages

Add:

* Scrapy crawler,
* Selenium extractor for JavaScript-heavy pages.

### V4 — Optional LLM Assistance

Add an optional LLM helper for:

* turning natural language goals into fields,
* suggesting selectors,
* summarizing reports.

The LLM will not control safety, authorization, or final validation decisions.
