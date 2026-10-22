# PartPilot Contracts (v1)

This file documents the **frozen** contract layer. Everything in this file was
verified against the installed packages on the build machine. Subagents must
follow it exactly and must not edit the frozen files.

## Frozen files (owned by the orchestrator only)

| File | Purpose |
| --- | --- |
| `backend/pyproject.toml` | Backend dependencies, ruff/black/pytest config. |
| `backend/shared/schemas.py` | All Pydantic models. |
| `backend/shared/interfaces.py` | All `typing.Protocol` interfaces. |
| `backend/shared/config.py` | `Settings` (pydantic-settings). |
| `backend/shared/db_schema.sql` | Reference SQL schema. |
| `contracts/openapi.yaml` | The API contract (OpenAPI 3.1). |
| `contracts/fixtures/**` | Recorded API responses, page samples, seed data, synthetic PDFs. |
| `frontend/package.json` | Frontend dependencies. |
| `frontend/src/api/types.ts` | TypeScript types generated from `openapi.yaml`. |
| `frontend/components.json`, `frontend/vite.config.ts`, `frontend/tsconfig*.json` | Frontend toolchain. |
| `Makefile` | Task runner. |

Anything you need that is not here: write a change request to
`docs/CHANGE_REQUESTS/<your-agent>-<n>.md` and keep going with a local
adapter. **Do not block.**

## Verified import paths (checked against the installed versions)

These were verified by importing them. Do not guess others.

```python
# LangChain 1.4.7 / langchain-core 1.6.13
from langchain.chat_models import init_chat_model          # NOT `from langchain import init_chat_model`
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.caches import InMemoryCache
from langchain_community.cache import SQLiteCache           # SQLiteCache is NOT in langchain_core.caches
from langchain_core.globals import set_llm_cache
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.fake_chat_models import (
    GenericFakeChatModel,      # test double
    FakeListChatModel,         # test double
    FakeMessagesListChatModel, # test double
)

# PDF (PyMuPDF 2.0)
import pymupdf                  # `import fitz` is deprecated and warns
import pdfplumber
```

Model construction (verified):

```python
model = init_chat_model(
    "openai:gpt-4o-mini",      # provider-prefixed form is preferred
    temperature=0.0,
    api_key=...,
    rate_limiter=InMemoryRateLimiter(requests_per_second=1.0, check_every_n_seconds=0.1, max_bucket_size=5),
)
retried = model.with_retry(stop_after_attempt=3)   # -> RunnableRetry
```

Provider strings accepted by `init_chat_model`: `openai`, `anthropic`,
`google_genai` (or `google_vertexai`), `bedrock`, `cohere`, `groq`, `ollama`,
`mistralai`, `xai`, `deepseek`, `fireworks`, `together`, `huggingface`.
Use the config value `Settings.llm_provider`; never hardcode a provider.

### The endpoint, the model and the key

The LangChain **OpenAI** provider talks to any OpenAI compatible endpoint, so
an OpenAI compatible gateway (for example OpenCode Zen, which serves free
models) works by changing three values in `.env`:

```bash
PARTPILOT_LLM_PROVIDER=openai
PARTPILOT_LLM_BASE_URL=http://127.0.0.1:1337/v1
PARTPILOT_LLM_MODEL=moonshotai/kimi-k2.6:free
PARTPILOT_LLM_API_KEY=your-zen-key
```

`PARTPILOT_LLM_BASE_URL` and `PARTPILOT_LLM_API_KEY` are **optional**. When
they are empty the provider uses its own default URL and the key from its own
environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...). A separate
`PARTPILOT_LLM_VISION_BASE_URL` points tier 3 at another endpoint when the
vision model lives elsewhere.

The secrets are `pydantic.SecretStr`, so their value never appears in a
`repr()`, a log line or a traceback (NFR-02). Read them with
`settings.llm_api_key.get_secret_value()`.

When the endpoint is unreachable or the key is missing, the search service
falls back to the deterministic filter builder in
`services/search.py:fallback_filter`. The fallback only ever *builds* a
filter - the database still chooses the rows - and it never guesses a
constraint it does not recognise.

## Distributor endpoints (verified against the vendor docs, 2026-10)

### DigiKey Product Information v4

* Token: `POST https://api.digikey.com/v1/oauth2/token`, form-encoded
  `client_id`, `client_secret`, `grant_type=client_credentials`.
  Access token lives 10 minutes (2-legged) / 30 minutes (3-legged).
* Headers on every call: `X-DIGIKEY-Client-Id`, `Authorization: Bearer <token>`,
  `X-DIGIKEY-Locale-Site`, `X-DIGIKEY-Locale-Language`, `X-DIGIKEY-Locale-Currency`.
* Endpoints:
  * `POST /products/v4/search/keyword`
  * `GET  /products/v4/search/{productNumber}/productdetails`
  * `GET  /products/v4/search/{productNumber}/pricing`
  * `GET  /products/v4/search/{productNumber}/media`
  * `GET  /products/v4/search/{productNumber}/substitutions`
  * `GET  /products/v4/search/categories`
* Limits: **120 requests/minute, 1000 requests/day**. Stay below. Cache
  everything. Never request the same part twice.

### Nexar (Octopart supply data, GraphQL)

* Token: `POST https://identity.nexar.com/connect/token`, form-encoded
  `grant_type=client_credentials`, `client_id`, `client_secret`,
  `scope=supply.domain`. Token lives 24 hours.
* GraphQL: `POST https://api.nexar.com/graphql`, header `Authorization: Bearer <token>`.
* Query names are **camelCase** and prefixed with `sup`:
  `supSearchMpn(q:, limit:)`, `supSearch(q:, filters:, sort:, start:)`,
  `supMultiMatch(queries:)`, `supParts(ids:)`, `supCategories`,
  `supManufacturers`, `supAttributes`.
* Free plan: 1000 parts per month (per application). Check the portal.

### Mouser Search API

* `POST https://api.mouser.com/api/v1/search/keyword?apiKey=<key>`
  body `{"SearchByKeywordRequest": {"keyword", "records", "startingRecord", "searchOptions"}}`
* `POST https://api.mouser.com/api/v1/search/partnumber?apiKey=<key>`
  body `{"SearchByPartRequest": {"mouserPartNumber": "A|B", "partSearchOptions": "Exact"}}`
  (up to 10 part numbers, pipe separated; matches manufacturer part numbers too)
* v2: `POST /api/v2/search/keywordandmanufacturer`,
  `POST /api/v2/search/partnumberandmanufacturer`,
  `GET  /api/v2/search/manufacturerlist`.
* Response: `{"Errors": [], "SearchResults": {"NumberOfResult": N, "Parts": [...]}}`
* Limits: **30 requests/minute, 1000 requests/day**. Max 50 records per call.

## Ethics rules that every collector must implement (plan section 12)

1. Official API first. Never scrape a distributor web page.
2. `robots.txt` is checked per host before a PDF download; a disallowed path is
   refused, not bypassed.
3. `User-Agent` is `Settings.user_agent` and contains a contact address.
4. At least `Settings.download_delay_seconds` (1 s) between requests to a host.
5. Every response is cached to disk with the date; a cache hit makes no request.
6. Never bypass bot protection, CAPTCHAs or login pages.
7. Datasheet PDFs are never committed to the repository and never republished.
   Only the extracted facts and a link to the source are stored.

## Tier rules (plan section 5.1)

| Tier | Method | Call it when |
| --- | --- | --- |
| 1 | table parser + regex | always first |
| 2 | LLM with a JSON schema over text and table data | tier 1 failed a field or the field failed validation |
| 3 | vision model over a page image | tier 2 failed, or the table is an image |

A higher tier is only called when the lower tier failed. The LLM never invents
a value: a value that is not present in the supplied text is a *failed field*,
not a guess (NFR-03).

## Confidence model (used by the validator, agent D)

```
base      = {tier1: 0.85, tier2: 0.75, tier3: 0.70, api: 0.90, manual: 1.00}[method]
checks    = 0.10 * (passed range check) + 0.05 * (passed min<=typ<=max) + 0.05 * (unit converted)
api_match = +0.05 when the API value agrees within tolerance, -0.10 when it disagrees
confidence = clamp(base + checks + api_match, 0.0, 1.0)
```

Status:

* `rejected` - the value is outside the allowed range for the field, or
  `min > typ > max`.
* `review` - confidence `< 0.75`, or the API value disagrees beyond tolerance,
  or the unit could not be converted, or the tier was 2/3.
* `accepted` - otherwise.

The exact numbers are the validator agent's business, but the *categories*
above are the contract.

## Units: the one rule that matters

**Every stored value is in a CANONICAL SI base unit.** There is exactly one
convention across the whole system:

| dimension | canonical unit | datasheet unit (source only) |
| --- | --- | --- |
| voltage | `V` | `mV` |
| current | `A` | `mA` |
| resistance | `ohm` | `mohm`, `kohm` |
| charge | `C` | `nC`, `uC` |
| capacitance | `F` | `pF`, `nF` |
| time | `s` | `ns`, `us` |
| temperature | `degC` | `degC` |
| thermal resistance | `degC/W` | `degC/W` |

Why: the alternatives finder compares two numbers with a relative distance.
If one part stored `rds_on` in `mohm` and another in `ohm`, the ranking would
be silently wrong. With one convention the comparison is always valid, and a
`ParameterConstraint` that arrives in a datasheet unit is converted before the
comparison.

So the units differ by LAYER, and this is intentional:

* **The source layer keeps the datasheet unit.** A raw DigiKey response says
  `"RDS(on) @ Id, Vgs": "12.0 mohm"`, a PDF table says `5.5 mOhm`, and the
  tier 1 extractor reads exactly what the document says.
* **Everything after the validator is canonical.** The validator normalises
  with `pint`; the database stores `0.012 ohm`; the services compare
  `0.012 ohm`; the API returns `0.012` with `"unit": "ohm"`.

The fixtures follow the same split:

| Fixture | Unit |
| --- | --- |
| `contracts/fixtures/digikey/*.json`, `nexar/*.json`, `mouser/*.json` | datasheet unit (what the vendor returns) |
| `contracts/fixtures/seed/parts.json` | **canonical** (it represents data that already passed the validator) |
| `contracts/fixtures/pdfs/expected_values.json` | datasheet unit (it is what the synthetic PDF says) |

`pint` and the private `db/units.py` helper produce bit-identical results for
the linear factors, so a value never changes when it crosses the boundary.

## Offers and stock

`contracts/fixtures/seed/parts.json` carries an `offers` list per part:

```json
"offers": [
  {"distributor": "digikey", "sku": "296-IRF3205S-ND", "stock": 10750,
   "unit_price": 3.1611, "currency": "USD", "url": "..."}
]
```

This is what the BOM health check needs for the `low_stock` and
`single_source` risks (FR-14) and what the alternatives ranking uses for its
stock bonus. The seed data is built so that the risks are reachable:

* `AOD4184A` is `nrnd` **and** single source (only DigiKey) -> `nrnd` +
  `single_source`.
* `IRF540N` has a DigiKey stock of 120 -> `low_stock`.
* every other part has two distributors.

## Fixture layout

```
contracts/fixtures/
  digikey/product_details.json       1 full DigiKey productdetails response
  digikey/keyword_search.json        1 DigiKey keyword search response
  digikey/parts.json                 10 normalised parts (5 MOSFET, 5 gate driver)
  nexar/supply_response.json         1 Nexar GraphQL response (data + errors)
  nexar/parts.json                   10 normalised parts
  mouser/partnumber_search.json      1 Mouser search response
  mouser/parts.json                  10 normalised parts
  pages/*.json                       5 extracted-page samples (text + tables)
  seed/parts.json                    30 seed parts
  seed/seed_parts.csv                same 30 parts as a CSV
  gold/gold_set_example.csv          12 labelled rows (gold-set template)
  pdfs/synthetic_mosfet.pdf          synthetic datasheet, known table
  pdfs/synthetic_gate_driver.pdf     synthetic datasheet, known table
  pdfs/synthetic_scanned.pdf         image-only PDF (no text layer)
  pdfs/expected_values.json          the exact values inside the synthetic PDFs
```

The fixtures are regenerated with:

```bash
backend/.venv/bin/python contracts/fixtures/generate_fixtures.py
```

## Commands

```bash
make test     # backend pytest + frontend vitest
make lint     # backend ruff/black + frontend eslint/prettier
make run-api  # uvicorn on 127.0.0.1:8000
make run-web  # vite on 127.0.0.1:5173
make mock-api # fastapi mock server that serves the OpenAPI file with fixtures
```
