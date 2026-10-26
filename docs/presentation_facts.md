# PartPilot — presentation facts (web scraping / data collection layer)

Everything below was verified directly in the code on 2026-10-26. Citations are
`file path · function/class`. Nothing is extrapolated; unverified points are
marked **NOT FOUND**. No secrets from `.env` are included.

---

## 1. Scraping / collection architecture

### 1.1 Data sources

| # | Source | Access | Auth | Endpoints | Owning module |
|---|--------|--------|------|-----------|---------------|
| 1 | DigiKey Product Information v4 | REST API (JSON) | OAuth2 *client credentials* (`POST /v1/oauth2/token`, form-encoded `client_id/secret/grant_type`); token cached with 60 s refresh margin (`TokenCache`) | `GET /products/v4/search/{mpn}/productdetails`, `/pricing`, `/media`, `/substitutions`; `POST /products/v4/search/keyword`; `GET /products/v4/search/categories` | `backend/collectors/digikey.py` · `DigiKeyCollector` (endpoints listed in module docstring, lines 1–20) |
| 2 | Nexar / Octopart supply | GraphQL API | OAuth2 client credentials at `https://identity.nexar.com/connect/token` (`scope=supply.domain`, 24 h token), then `Authorization: Bearer` to `https://api.nexar.com/graphql` | `supSearchMpn`, `supSearch`, `supMultiMatch`, `supParts`, `supCategories`, `supManufacturers` (query constants lines 87–152) | `backend/collectors/nexar.py` · `NexarCollector.graphql` |
| 3 | Mouser Search API | REST API (JSON POST) | API key in the **query string** (`?apiKey=...`); key excluded from cache keys and redacted from httpx log lines | `POST /api/v1/search/partnumber` (≤10 pipe-separated MPNs), `POST /api/v1/search/keyword`; v2: `search/partnumberandmanufacturer`, `search/manufacturerlist` | `backend/collectors/mouser.py` · `MouserCollector._post`, `_ApiKeyRedactingFilter` |
| 4 | SearXNG (self-hosted metasearch) | JSON API of own instance (`GET {endpoint}/search?q=...&format=json&categories=general`) | none (self-hosted); clear `User-Agent: PartPilot/0.1` | two query variants per MPN in datasheet resolution: `"<mfr> <mpn> datasheet filetype:pdf"`, `"<mfr> <mpn> datasheet pdf"` | `backend/services/web_search.py` · `WebDiscoveryService.discover`; `backend/collectors/datasheets.py` · `DatasheetResolver._candidate_urls` (lines 473–504) |
| 5 | India HTML scrapers (element14 India, Robu.in, Evelta) | Raw HTML scraping with BeautifulSoup; **robots.txt deliberately bypassed** (`BaseWebScraper` docstring: "Does not enforce robots.txt") | none; browser Chrome UA spoofed (`DEFAULT_SCRAPER_USER_AGENT`, `base_scraper.py` lines 18–21) | `https://in.element14.com/search?st=<MPN>`, `https://robu.in/?s=<MPN>&post_type=product`, `https://www.evelta.com/search.php?search_query=<MPN>` | `backend/collectors/scrapers/{base_scraper,element14,robu,evelta}.py`; coordinator `india_hub.py` · `IndiaSourcesHub.scrape_all_sources_for_part` (parallel `asyncio.gather`) |
| 6 | Datasheet PDF hosts (manufacturer/distributor) | Direct HTTP GET of the PDF file | none; PartPilot UA first, **falls back to browser UA on HTTP 401/403** (`datasheets.py` lines 205–218) | Any URL returned by APIs/SearXNG; candidate ranking prefers `.pdf`, "datasheet", trusted domains (ti.com, st.com, infineon.com, … — `DatasheetResolver._TRUSTED_DOMAINS`) | `backend/collectors/datasheets.py` · `DatasheetDownloader.download_async`, `DatasheetResolver` |
| 7 | Bundled seed fixtures (offline) | Local JSON (`contracts/fixtures/seed/parts.json`, 30 synthetic parts) | none | none (no network) | `backend/collectors/seeds.py` · `load_bundled_seed`, `build_seed_list` (API first, bundled list as fallback, lines 127–166) |

**NOT FOUND**: a per-month part counter for the Nexar free plan ("1000 parts
per month" in `docs/ETHICS.md` §3) — the code only enforces per-minute and
per-day budgets (`RateLimiter` in `collectors/base.py`).

### 1.2 Request/response shapes

- DigiKey: normalisation from `Product` document — `ManufacturerProductNumber`,
  `Manufacturer.Name`, `Description.DetailedDescription`, `Parameters.Parameter[]`
  (`ParameterText`/`ValueText`), `ProductVariations[].StandardPricing[]`
  (`BreakQuantity`, `UnitPrice`) — in `digikey.py` · `normalize_product`
  (lines 236–344) and `_offers_from_product` (lines 387–418).
- Nexar: `part` objects with `specs[{attribute{name,shortname}, value,
  displayValue, unitsName}]` and `sellers[].offers[].prices[]`; field selection
  in `_PART_FIELDS` constant (`nexar.py` lines 58–85), normalisation in
  `normalize_part` / `_parameters` (lines 315–391, "first row with a number wins").
- Mouser: `SearchResults.Parts[]` with `ProductAttributes[]`, `PriceBreaks[]`,
  `AvailabilityInStock` (string "48213"), `IsDiscontinued` (string "true"/"false"
  — parsed by `parse_bool`, `mouser.py` lines 94–111).
- All three normalise into the same frozen Pydantic `PartRecord`
  (`part_id = "<family>-<slug>"`, `source_id = "api-<distributor>-<slug>"`,
  `ParameterValue(...method=API, confidence=0.90)` — `API_CONFIDENCE` in each
  collector). Collector protocol: `search_by_mpn`, `search_by_keyword`,
  `get_offers`, each with `async` core + `run_sync` wrapper (`collectors/base.py`
  lines 127–143).

### 1.3 End-to-end flow (query → extraction)

1. **User query** hits the search service (`backend/services/search.py` ·
   `SearchService.search`, lines 908–924).
2. **Filter build**: LLM builds a `SearchFilter` inside a 4 s budget
   (`_call_with_budget`, lines 603–624); on failure/timeout a deterministic
   regex fallback builds it (`fallback_filter`, lines 177–381). The LLM never
   selects rows — the repository executes the filter.
3. **Source discovery, in parallel worker threads with a 12 s budget**
   (`_execute`, lines 793–811):
   - scraped hits + raw pages via `WebDiscoveryService.discover_and_ingest_with_results`
     (`_discover_scraped_with_budget`, lines 648–670);
   - API hits via `ProviderDiscoveryService.discover_and_ingest` (DigiKey +
     Mouser + Nexar keyword search in a thread pool, merge/dedup by MPN —
     `backend/services/provider_discovery.py` lines 36–67); only enabled when
     `PARTPILOT_PROVIDER_API_DISCOVERY_ENABLED=true` (`app/wiring.py` lines 103–122).
4. **SearXNG fetch + safety gate**: results filtered by blocklist
   (`is_blocked`), trusted-domain or electronics-term check (`is_trusted_domain`),
   MPN validity (`validate_mpn`) — `backend/services/web_search.py` lines
   97–179, 189–251.
5. **Optional page fetch**: `_scrape_candidates` fetches pages with httpx +
   BeautifulSoup (≤4 parallel workers, text capped at 3000 chars, blocked
   content dropped, ≥2 electronics terms required) — `web_search.py` lines
   718–761; India distributor offers attached via `IndiaSourcesHub`
   (`_attach_distributor_offers`, lines 763–805).
6. **Ingestion**: verified candidates are written as `PartRecord` +
   `SourceRef` into SQLite (`repository.add_part`/`add_source`,
   `backend/db/repository.py` lines 293–331).
7. **Merge & re-query**: repository results re-listed after discovery;
   dedup by `mpn` (`seen_mpns`); everything ranked by `services/ranker.rank_parts`
   (`search.py` lines 805–870).
8. **Zero-hit on-demand discovery**: if 0 hits, `ComponentAdvisorService.
   discover_and_ingest` runs, then a relaxed `mpn_contains` filter
   (`search.py` lines 844–857).
9. **Datasheet download (async path)**: `services/jobs.py` ·
   `BackgroundJobRunner._prepare_request` resolves `pdf_path` from the request,
   the part's stored PDF source, or `DatasheetResolver.resolve_and_download`
   (lines 222–300). Failure raises `ValueError("pdf_path is required")`.
10. **Extraction pipeline**: tier 1 rules → tier 2 (LLM text) → tier 3 (LLM
    vision) with merge of failed fields (`_extract`, lines 304–388), then
    validation (`_validate`) and storage (`_store`) — §3 below.

Streaming variant of the same flow with progressive events
(`filter` → `local_results` → `web_results` → `discovered_results` →
`advisory` → `done`) is `SearchService.stream_search` (lines 944–1090).

---

## 2. Scraping engineering details

All in `backend/collectors/base.py` unless noted.

- **Rate limiting** — `RateLimiter` (lines 179–285): per-minute *and* per-day
  budgets below documented limits (DigiKey 60/min + 800/day vs documented
  120/min + 1000/day; Mouser 20/min + 800/day; Nexar 60/min + 800/day —
  `shared/config.py` lines 114–121 and `.env.example`). Daily budget is a hard
  stop raising `RateLimitExceededError`; the minute window can be waited on
  with `block=True`. Clock/sleep are injectable for tests.
- **Retries / backoff** — `RetryPolicy` (lines 410–494): tenacity,
  `stop_after_attempt(max_retries=4)`, exponential wait (multiplier
  `retry_backoff_seconds=0.5`, cap 30 s). Retries only HTTP 429 + 5xx
  (`RetryableStatusError`) and `httpx.TransportError`; other 4xx raise
  `HttpStatusError` immediately (`status_to_error`, lines 541–552).
- **Timeouts** — one httpx client factory with
  `request_timeout_seconds=30.0` (`make_async_client`, lines 160–171);
  web-search timeout 4 s, web-discovery budget 12 s (`shared/config.py`
  lines 69–71).
- **Caching** — `DiskCache` (lines 315–401): every raw API response stored at
  `data/raw/<namespace>/<YYYY-MM-DD>/<sha256(key)>.json`; lookups check today's
  dir, then older ones, so "the same part is never requested twice". Cache key
  = method + URL + params/body (`cache_key`, line 590). Mouser cache keys never
  contain the API key (`mouser.py` line 164). Hit/miss stats in `CacheStats`.
- **Deduplication** — by MPN in `ProviderDiscoveryService.discover_and_ingest`
  (key `mpn.lower()`, merge offers + keep the record with more parameters);
  by `seen_mpns` in search result assembly; Nexar spec rows deduped by
  standard name (`_parameters`, `seen` dict).
- **Concurrency** — async httpx throughout the collectors; sync facade via
  `run_sync` (fresh loop or worker thread). Parallel source fan-out with
  `ThreadPoolExecutor` (`provider_discovery.py` line 39), ≤4 scraping workers
  (`web_search.py` line 757), `asyncio.gather` across the three India scrapers
  (`india_hub.py` line 42).
- **User-Agent handling** — clear UA string
  `PartPilot/0.1 (academic research; component data mining; contact:
  partpilot-contact@example.edu)` (`shared/config.py` lines 129–132,
  `.env.example`). Exception: India scrapers send a spoofed Chrome UA
  (`base_scraper.py` lines 18–21); datasheet downloader retries 401/403 with a
  browser UA (`datasheets.py` lines 205–218).
- **robots.txt / ToS / ethics** — `docs/ETHICS.md` states the rules (official
  APIs first; no CAPTCHA/paywall bypass; 1 s per-host delay; facts-not-PDFs;
  keys stay server-side; LLM never invents values). In code:
  `DatasheetDownloader.is_allowed` fetches `robots.txt` per host, caches the
  policy, refuses disallowed paths with `RobotsDisallowedError` semantics
  (`datasheets.py` lines 99–157). **But** the default is overridden:
  `.env.example` ships `PARTPILOT_RESPECT_ROBOTS_TXT=false` and
  `docs/ETHICS.md` §3 documents that India multi-source scraping runs with
  robots disabled. `bypass_robots=not settings.respect_robots_txt` is passed in
  `DatasheetResolver.resolve_and_download` (line 440).
- **Error handling** — `CollectorError` hierarchy (`MissingCredentialsError`,
  `RateLimitExceededError`, `RetryableStatusError`, `HttpStatusError`,
  `RobotsDisallowedError`, `InvalidPdfError`, base.py lines 81–114). Collector
  failures are logged and returned as `None` (e.g. `digikey.py`
  `search_by_mpn_async` lines 423–448); the downloader never raises out
  (`datasheets.py` line 254).
- **Offline fixtures / deterministic fallbacks** — fixtures in
  `contracts/fixtures/{digikey,nexar,mouser,seed,pdfs,pages}`; respx-mocked
  tests (`tests/collectors/test_digikey.py`); bundled seed list fallback
  (`seeds.py` lines 154–166); India scrapers fall back to hard-coded catalogs
  (`ELEMENT14_FALLBACK_CATALOG`, `ROBU_FALLBACK_CATALOG`,
  `EVELTA_FALLBACK_CATALOG`) and then to a generic default offer; LLM search
  falls back to `fallback_filter`; dry-run mode in the manual collector
  (`collectors/manual/collect_manual.py --dry-run`); fixture-backed mock API
  (`backend/tools/mock_api.py`, docker-compose `mock-api` profile).
- **Same-host politeness** — `DatasheetDownloader._wait_for_host` enforces
  ≥ `download_delay_seconds` (default 1.0 s) between two requests to one host
  (`datasheets.py` lines 162–172).

### Datasheet PDF lifecycle (`collectors/datasheets.py`)

1. **Locate** — `DatasheetResolver.resolve_and_download` (lines 401–445):
   synthetic fixtures for demo MPNs (PMP100*/PGD35*), the indexed
   `datasheet_url`, DigiKey keyword-search datasheet URLs (score 98),
   SearXNG `filetype:pdf` queries, all scored by `_score_candidate`
   (line 515: +60 `.pdf` path, +25 "datasheet" text, +30 trusted domain,
   +10 download-ish path; MPN must appear in the text).
2. **Permission** — robots check per host (unless disabled), http(s) only
   (line 185).
3. **Download** — with retry policy and per-host delay; UA fallback on 401/403.
4. **Validate** — `%PDF-` magic bytes must be at the start or within the first
   1024 bytes (garbage prefix is stripped, lines 222–231); **PyMuPDF must open
   the stream** and report a page count (`_count_pages_of_bytes`, lines
   269–277); HTML error pages are rejected.
5. **Store** — content-addressed: `data/pdfs/<sha256>.pdf` (`_store`,
   lines 258–267). Parts sharing a datasheet share the hash, hence the
   `source_id` `pdf-<hash>` and the `group_by_hash` helper (lines 351–361).
6. **Provenance** — a `SourceRef(source_id=f"pdf-{digest}", file_hash, page_count,
   local_path, distributor=host)` is returned and indexed
   (lines 240–253). `is_scanned` detects a missing text layer → routes to tier 3
   (lines 327–342).

### Cross-supplier normalisation & cross-validation

- Same `PartRecord`/`ParameterValue` schema for all three APIs
  (`shared/schemas.py` lines 116–210).
- Vendor labels → 25 standard names via `collectors/params.py` ·
  `resolve_parameter_name` (exact `ALIASES`/`SHORTNAME_ALIASES` maps; optional
  rapidfuzz ≥95, off by default — unknown labels are **dropped, never guessed**,
  lines 398–430).
- Values parsed with `parse_value_with_unit` + `canonical_unit` (UNIT_ALIASES
  map, lines 250–311); test conditions extracted from labels with
  `parse_condition` (`"RDS(on) @ Id, Vgs"` → `{"Id": "specified", ...}`).
- Cross-validation of extracted-vs-API values happens in the validator
  (`validation/validator.py` · `validate_with_reasons`, lines 155–338): the API
  value of the same parameter name is compared with the extracted value within
  the field tolerance (`values_agree`, `tolerance_for` from
  `validation/rules.py`); match adds +0.05 confidence, mismatch −0.10 and a
  review flag.

---

## 3. Post-scraping pipeline (brief)

- **Tier 1 (rules)** — `extraction/tier1/extractor.py` · `PdfTier1Extractor`:
  pdfplumber table extraction over pages found by `page_finder.find_pages`;
  stores a value only when read unambiguously from a table cell; unreadable
  fields go to `failed_fields`, scanned PDFs yield nothing and are handed to
  tier 3 (module docstring lines 1–19). Base confidence 0.85.
- **Tier 2 (LLM text) / Tier 3 (LLM vision)** —
  `extraction/llm/extractor.py` · `LLMExtractorImpl`: tier 2 reads page text +
  table rows, tier 3 reads rendered page images (`services/jobs.py`
  `_page_images`, max 3 pages); every call recorded for cost accounting
  (`llm/recorder.py`, `llm_calls` table); every field the model did not fill
  becomes a failed field, never a guess (module docstring lines 1–17).
  Tier routing and tier-2 supplementation of tier-1 failed fields:
  `services/jobs.py` · `_extract` (lines 304–388).
- **Unit normalisation** — `validation/units.py`: exactly one `pint`
  UnitRegistry; canonical units V/A/ohm/F/C/s/degC/degC/W; unknown units return
  `(None, None)` → review, never raise (`normalize`, lines 231–295); ambiguous
  "C" resolved via `expected_unit` hint.
- **Confidence scoring** — `validation/confidence.py` · `compute_confidence`:
  `base {tier1 0.85, tier2 0.75, tier3 0.70, api 0.90, manual 1.00}` +
  `0.10·range + 0.05·ordering + 0.05·unit-converted ± API check`
  (+0.05 / −0.10), clamped to [0,1]; below `REVIEW_THRESHOLD = 0.75` a value
  always goes to review.
- **Provenance** — every value carries `source_id`, `page`, `method`,
  `confidence`, `condition`, `raw_text` (`shared/schemas.py` ·
  `ParameterValue`, lines 174–210). **Bounding box: NOT FOUND** — the schema
  has page-level provenance only; no bbox field exists anywhere in the backend.
- **Review queue** — values with status `review` are listed least-confident
  first (`db/repository.py` · `list_review_queue`, lines 914–928); a decision
  (`accept`/`correct`/`reject`) sets `method=manual`, `confidence=1.0`, and
  writes to `review_corrections` for feedback into the name map
  (`apply_review`, lines 963–983; service wrapper
  `services/review.py` · `ReviewService`).

---

## 4. Data model

SQLAlchemy models in `backend/db/models.py` (mirror `shared/db_schema.sql`):

| Table | Key fields |
|---|---|
| `parts` (`PartRow`, lines 68–104) | `part_id` PK, `mpn`, `manufacturer`, `family` (CHECK: mosfet/gate_driver), `package`, `lifecycle_status`, `datasheet_url`, `description`, `source_ids` (JSON), UNIQUE(mpn, manufacturer) |
| `sources` (`SourceRow`, 107–128) | `source_id` PK, `url`, `type` (CHECK: api/pdf/manual), `file_hash`, `distributor`, `page_count`, `local_path`, `content_type`, `note` |
| `parameters` (`ParameterRow`, 131–182) | `param_id` PK, `part_id` FK, `name`, `value`/`value_min`/`value_typ`/`value_max`, `unit`, `condition` (JSON), `source_id` FK, `page`, `method` (CHECK: tier1/tier2/tier3/api/manual), `confidence` (0–1 CHECK), `status` (CHECK: accepted/review/rejected), `raw_text`, `value_text` |
| `offers` (`OfferRow`, 185–212) | `offer_id` PK, `part_id` FK, `distributor`, `sku`, `stock`, `unit_price`, `currency`, `price_breaks` (JSON), `lead_time_days`, `url`, `fetched_at` |
| `name_map` (`NameMapRow`, 215–236) | `raw_name`+`family` UNIQUE → `standard_name`, `approved` (yes/no) — human-approved label mapping |
| `llm_calls` (`LLMCallRow`, 239–270) | `chain`, `model`, `tokens_in/out`, `cost`, `prompt_version`, `cached`, `duration_ms` (NFR-05 cost accounting) |
| `review_corrections` (`ReviewCorrectionRow`, 273–288) | `param_id`, `action`, `old_value`, `new_value`, `note` |

Example record (synthetic fixture data, `contracts/fixtures/seed/parts.json`):

```json
{
  "part_id": "mosfet-irf3205s",
  "mpn": "IRF3205S",
  "manufacturer": "International Rectifier",
  "family": "mosfet",
  "package": "TO-220AB",
  "lifecycle_status": "active",
  "source_ids": ["api-digikey-irf3205s", "api-nexar-irf3205s"],
  "parameters": {
    "vds_max":  {"value": 56.0, "unit": "V", "condition": {}},
    "rds_on":   {"value": 0.012, "unit": "ohm",
                 "condition": {"Vgs": "10 V", "Id": "2 A", "Tj": "25 C"}},
    "vgs_threshold": {"value": 2.47, "unit": "V", "condition": {"Id": "250 uA"}}
  }
}
```

---

## 5. Concrete examples (fixtures / eval)

1. **DigiKey API → normalised part** — fixture
   `contracts/fixtures/digikey/product_details.json` (`Product`):
   `ManufacturerProductNumber "IRF3205S"`, parameter
   `"Drain to Source Voltage (Vdss)" = "56.0 V"`, price breaks
   `1×$0.89, 10×$0.674, 100×$0.5223, 1000×$0.4121`, stock 48213.
   `DigiKeyCollector.normalize_product` maps the label via
   `resolve_parameter_name` → `vds_max`, `parse_value_with_unit` →
   `(56.0, "V")`, `method=api`, `confidence=0.90`, `source_id
   api-digikey-irf3205s`. Gold-set row for the same part:
   `mosfet-irf3205s,vds_max,56.0,V`
   (`contracts/fixtures/gold/gold_set_example.csv` line 2).
2. **Nexar GraphQL → parameter parsing** — fixture
   `contracts/fixtures/nexar/supply_response.json`: `supSearchMpn` returns part
   `DMN3024U-13` (Diodes Incorporated, 30 V) whose `specs` carry the same
   attribute three times (30/40/20 V rows). `NexarCollector._parameters`
   docstring + code (lines 347–391): "The first row that carries a number
   wins; a row without a number is never used" → one `vds_max = 30.0 V`.
3. **Mouser API → offer parsing** — fixture
   `contracts/fixtures/mouser/partnumber_search.json`: part `UCC27511`,
   `"AvailabilityInStock": "48213"` (string), `"LeadTime": "84 Days"`,
   `"IsDiscontinued": "false"`. `MouserCollector._offers` (lines 340–379)
   parses stock with `int(str.replace(",",""))`, price `"0.89"` → 0.89 USD
   via `parse_value_with_unit`, lead time 84 via regex `_lead_time`;
   `parse_bool` handles the string booleans.
4. **Query → filter (eval)** — `eval/queries.py` line 47: query
   *"100 V N-channel MOSFET with Rds(on) below 5 mOhm, in stock"* must yield
   `{"family": "mosfet", "in_stock": true, "parameters":
   [{"name": "rds_on", "unit": "mohm", "max": 5.0}]}` — this is exactly what
   `fallback_filter` builds (`services/search.py` lines 249–290).
5. **Eval demo run** — `eval/results/demo_results.json` (generated
   2026-10-22): 12 parts × 48 fields; field accuracy tier1 35.4% (cost $0),
   tier2-tables 77.1% ($0.072), tier3 93.75% ($0.60, ~$0.05/datasheet).

---

## 6. Numbers I can quote

All verified by running commands (offline, no network):

- **Tests**: `cd backend && .venv/bin/python -m pytest --collect-only -q`
  → **778 tests collected**. `pytest ../eval --collect-only -q`
  → **102 tests collected**. Total **880**.
  Collector-related subsets: `tests/collectors/*` = 102 tests (base 13,
  datasheets 13, digikey 13, mouser 15, nexar 7, params 31, protocols 4,
  seeds 6).
- **Data sources**: 3 official APIs (DigiKey v4, Nexar GraphQL, Mouser) +
  1 SearXNG metasearch + 3 India HTML scrapers (element14_in, robu_in,
  evelta_in) + datasheet PDF downloader + bundled seed fixtures = **9 distinct
  inputs**; `DefaultCollectorBundle.FAMILY_COLLECTORS` maps MOSFET→
  (digikey, nexar), GATE_DRIVER→(digikey, mouser, nexar)
  (`collectors/bundle.py` lines 25–28).
- **Parameters**: **25** standard parameter names with validation rules
  (`validation/rules.py` · `FIELD_RULES`, verified by import: 25 rules);
  13 MOSFET fields + 13 gate-driver fields (`collectors/params.py`
  `MOSFET_PARAMS`/`GATE_DRIVER_PARAMS`).
- **Families** with dedicated parameter sets in search: MOSFET, GATE_DRIVER,
  OPAMP, REGULATOR, MCU, GENERAL (`services/search.py` lines 67–126).
- **Eval queries**: **30** golden natural-language queries
  (`eval/queries.py`, `QUERY_COUNT = 30`).
- **Eval demo metrics** (`eval/results/demo_results.json`, demo/fake
  implementations, 12 parts / 48 fields): tier1 35.4%, tier2 text 47.9%,
  tier2 tables 77.1%, tier3 93.75% field accuracy; costs $0 / $0.048 / $0.072 /
  $0.60 respectively.
- **Gold set target** (plan, `docs/GOLD_SET.md`): 80 parts, ≥5 manufacturers,
  10–15 fields/part, 20% double-labelled. The committed example gold set is
  `contracts/fixtures/gold/gold_set_example.csv` (small subset).
- **Seed**: 30 synthetic parts (15 MOSFET, 15 gate driver) in
  `contracts/fixtures/seed/parts.json` (verified by loading the JSON).

---

## 7. Limitations and honest trade-offs (visible in code)

- **robots.txt bypass for India scraping**: `BaseWebScraper` explicitly does
  not enforce robots.txt and spoofs a Chrome UA
  (`base_scraper.py` docstring lines 3–6, 18–21); `.env.example` sets
  `PARTPILOT_RESPECT_ROBOTS_TXT=false`. This is a deliberate trade-off against
  `docs/ETHICS.md` §1 ("It never scrapes a distributor web page") — the doc and
  the scrapers contradict each other.
- **Fabricated fallback data**: the India scrapers always return an `Offer`,
  even when the live scrape fails — hard-coded catalogs plus a generic default
  (element14: stock 1200, ₹160; robu: 150, ₹65; evelta: 200, ₹55)
  (`element14.py` lines 110–140, `robu.py` 109–139, `evelta.py` 93–123).
  `WebDiscoveryService.deep_scrape_part` **synthesises** Mouser/LCSC offers
  with fixed stock (14520 / 38900) and prices derived from a hard-coded
  `ref_price = 1.85` (`web_search.py` lines 633–678); scraped offers get a
  default price of `1.25` and stock `2500` when regexes fail (lines 288–298).
  These are demo values, not real market data.
- **Silent family assumption**: when the family cannot be inferred, collectors
  log a warning and **assume MOSFET** (`digikey.py` lines 369–370,
  `nexar.py` 429–430, `mouser.py` 337–338).
- **DB family CHECK only allows mosfet/gate_driver** (`models.py`
  `ck_parts_family`, line 73) although web discovery can emit
  MCU/OPAMP/REGULATOR families (`web_search.py` `_infer_family`) — those
  ingested web parts can violate the SQLite CHECK constraint.
- **API-quota dependence**: provider API discovery is off by default
  (`provider_api_discovery_enabled=false` in `.env.example`); without keys the
  live path is SearXNG + scrapers only.
- **Nexar free-plan limit** (1000 parts/month, `docs/ETHICS.md` §3) is not
  enforced in code — **NOT FOUND** a monthly counter.
- **Fragile HTML scraping**: the India scrapers parse with loose CSS selectors
  (`.product, .card`, `tr.productRow`) and invent default price/stock when a
  selector misses (`element14.py` lines 163–181, `evelta.py` lines 142–157);
  site redesigns will silently produce fabricated-looking defaults.
- **Bot-protection workaround tension**: the PDF downloader retries 401/403
  with a browser UA (`datasheets.py` lines 205–218), while `docs/ETHICS.md` §5
  says no bot-protection bypass ("never bypasses a CAPTCHA, a bot protection…").
- **In-memory job registry**: background jobs are lost on restart
  (`services/jobs.py` module docstring lines 1–9).
- **Hard-coded limits**: Mouser ≤10 MPNs/call, ≤50 records/call
  (`MAX_PART_NUMBERS`, `MAX_RECORDS`, `mouser.py` lines 63–67); DigiKey keyword
  limit clamped to 100 (`digikey.py` line 220); search pagination capped at
  limit 500 / offset 10000 (`MAX_LIMIT`/`MAX_OFFSET`, `search.py` lines 56–57);
  LLM filter budget 4 s; web discovery budget 12 s; in-memory search rate
  limit 30/min (`search_rate_limit_per_minute`).
- **No bounding-box provenance** for extracted values (page number only) —
  NOT FOUND in the schema.
- **No explicit TODO/FIXME markers** found in backend source (grep returned
  none outside tests/venv).

---

## 8. Slide-worthy snippets (≤15 lines each)

### 8.1 Disk cache — "a cache hit never touches the network"
`backend/collectors/base.py` · `DiskCache.get` (365–380)

```python
def get(self, key: str) -> Any | None:
    digest = self.hash_key(key)
    candidates = [self.path_for(key)]
    candidates.extend(d / f"{digest}.json" for d in self.dated_dirs())
    for candidate in candidates:
        if candidate.is_file():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("cache file %s is unreadable, ignoring it", candidate)
                continue
            self._stats.hits += 1
            return payload
    self._stats.misses += 1
    return None
```

### 8.2 Retry policy — "429/5xx retry, other 4xx never"
`backend/collectors/base.py` · `status_to_error` (541–552)

```python
def status_to_error(response: httpx.Response) -> None:
    """* 429 and 5xx raise RetryableStatusError (the caller retries).
    * every other 4xx raises HttpStatusError (never retried)."""
    if response.status_code < 400:
        return
    detail = response.text[:300] if response.status_code != 429 else ""
    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableStatusError(response.status_code, detail)
    raise HttpStatusError(response.status_code, detail)
```

### 8.3 Daily quota is a hard stop
`backend/collectors/base.py` · `RateLimiter.acquire` (253–278)

```python
def acquire(self, *, block: bool = False) -> None:
    if self.try_acquire():
        return
    self._prune()
    if self._day_calls >= self.per_day:
        raise RateLimitExceededError(
            f"{self.name}: daily budget of {self.per_day} requests is exhausted")
    if not block:
        raise RateLimitExceededError(...)
    while not self.try_acquire():
        self._prune()
        if self._day_calls >= self.per_day:
            raise RateLimitExceededError(...)
        oldest = self._minute_calls[0] if self._minute_calls else self._clock()
        wait = max(0.0, 60.0 - (self._clock() - oldest))
        self._sleep(wait)
```

### 8.4 PDF validation — magic bytes + PyMuPDF + content-addressed storage
`backend/collectors/datasheets.py` · `download_async` (221–239)

```python
content = response.content
if not (content.startswith(PDF_MAGIC) or (b"%PDF-" in content[:1024])):
    logger.warning("refusing %s: the body is not a PDF (starts with %r)",
                   url, content[:16])
    return None
idx = content.find(b"%PDF-")
if idx > 0:
    content = content[idx:]
digest = hashlib.sha256(content).hexdigest()
page_count = self._count_pages_of_bytes(content)
if page_count is None:
    logger.warning("refusing %s: PyMuPDF cannot open the body", url)
    return None
path = self.settings.pdf_dir / f"{digest}.pdf"
```

### 8.5 Multi-provider merge & dedup
`backend/services/provider_discovery.py` · `discover_and_ingest` (39–58)

```python
with ThreadPoolExecutor(max_workers=len(self._collectors)) as pool:
    futures = [pool.submit(self._search_one, c, query, limit)
               for c in self._collectors]
    batches = [future.result() for future in futures]
merged: dict[str, PartRecord] = {}
for batch in batches:
    for record in batch:
        key = record.mpn.strip().lower()
        current = merged.get(key)
        if current is None:
            merged[key] = record
            continue
        current.offers.extend(o for o in record.offers
                              if o.distributor not in {i.distributor for i in current.offers})
        if len(record.parameters) > len(current.parameters):
            current.parameters = record.parameters
        current.source_ids = list(dict.fromkeys([*current.source_ids, *record.source_ids]))
```

### 8.6 Datasheet candidate scoring (SearXNG → ranked PDF candidates)
`backend/collectors/datasheets.py` · `DatasheetResolver._score_candidate` (515–532)

```python
@classmethod
def _score_candidate(cls, url, title, content, mpn) -> int:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    path = parsed.path.lower()
    text = f"{title} {content} {path}"
    if mpn.lower() not in text and mpn.lower().replace("-","") not in text.replace("-",""):
        return 0
    score = 10
    if path.endswith(".pdf") or ".pdf?" in url.lower():
        score += 60
    if "datasheet" in text or "data sheet" in text:
        score += 25
    if any(host == d or host.endswith(f".{d}") for d in cls._TRUSTED_DOMAINS):
        score += 30
    if re.search(r"download|document|lit/|resource|documentation", path):
        score += 10
    return score
```

### 8.7 API key redaction in logs (bonus)
`backend/collectors/mouser.py` · `_ApiKeyRedactingFilter` (70–80)

```python
class _ApiKeyRedactingFilter(logging.Filter):
    """Remove ``apiKey=...`` from every log record of the httpx loggers."""
    _pattern = re.compile(r"apiKey=[^&\s\"']+")
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "apiKey=" in message:
            record.msg = self._pattern.sub("apiKey=***", message)
            record.args = ()
        return True
```
