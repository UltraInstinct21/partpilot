# HANDOFF - API layer (agent G, WP6)

Branch: `agent/g-api`. Everything below lives in `backend/app/` and
`backend/tests/api/`.

## 1. What exists

| File | Purpose |
| --- | --- |
| `app/main.py` | `create_app()` and the `app` object for `uvicorn app.main:app`. CORS, the exception handlers, the OpenAPI customisation. |
| `app/wiring.py` | **The composition root.** `FACTORIES` maps every collaborator to a factory. This is the only file the integration phase changes. |
| `app/container.py` | The dataclass that holds every collaborator. |
| `app/dependencies.py` | The FastAPI `Depends` providers. Every route gets its collaborator from here. |
| `app/errors.py` | The global handlers. Every error is `{"detail": "...", "code": "..."}`. |
| `app/rate_limit.py` | `FixedWindowRateLimiter` for `POST /api/search`. |
| `app/pdf.py` | Renders one page of a PDF to a PNG with PyMuPDF. |
| `app/params.py` | Small helpers for the query parameters. |
| `app/schemas.py` | The few response shapes the contract has but `shared.schemas` does not (`ParameterSource`, `HealthResponse`). |
| `app/routes/` | One module per group of endpoints. `ROUTERS` in `app/routes/__init__.py` lists them all. |
| `app/fakes/` | The in-memory implementations so the API runs before the other agents land. |
| `tests/api/` | 91 tests: one file per endpoint group plus the Schemathesis contract test. |

## 2. How to run

```bash
cd backend
.venv/bin/python -m pytest -q            # 91 passed
.venv/bin/python -m ruff check .         # clean
.venv/bin/python -m black --check .      # clean
.venv/bin/python -m uvicorn app.main:app --port 8000
```

## 3. How to swap the fakes for the real implementations

`app/wiring.py` is the only file that changes. `FACTORIES` maps a name to a
factory; a factory may accept any subset of `settings`, `repository`,
`llm_extractor`, `tier1_extractor` and `validator`, and only the arguments it
declares are passed (`_call` inspects the signature).

The real implementations, with the signatures this layer expects:

| Key | Real implementation | Constructor |
| --- | --- | --- |
| `repository` | `db.repository.SqlAlchemyPartsRepository` | `SqlAlchemyPartsRepository(engine)` |
| `llm_extractor` | `extraction.llm.extractor.LLMExtractorImpl` | `LLMExtractorImpl(model=None, recorder=None, settings=None)` |
| `tier1_extractor` | `extraction.tier1.extractor.PdfTier1Extractor` | `PdfTier1Extractor(settings=None)` |
| `validator` | `validation.validator.ParameterValidator` | `ParameterValidator(settings=None)` |
| `search_service` | `services.search.SearchService` | `SearchService(repository, llm=None, *, max_limit=200, max_offset=10_000)` |
| `alternatives_service` | `services.alternatives.AlternativesService` | `AlternativesService(repository, llm=None, *, ...)` |
| `bom_service` | `services.bom.BomService` | `BomService(repository, *, low_stock_threshold=1000, single_source_max=1)` |
| `review_service` | `services.review.ReviewService` | `ReviewService(repository)` |
| `stats_service` | `services.stats.StatsService` | `StatsService(repository)` |
| `job_runner` | `services.jobs.BackgroundJobRunner` | `BackgroundJobRunner(repository, tier1=None, llm=None, validator=None, *, background_tasks=None, pages_provider=None, max_jobs=200)` |

The other agents build these against `shared/interfaces.py`, so the exact
signatures are also in `shared/interfaces.py`.

## 4. The endpoints

All twelve endpoints of `contracts/openapi.yaml` are implemented, plus
`GET /health` (a liveness probe that is **not** in the frozen contract; it is
the only deliberate deviation and it is documented in the OpenAPI description).

* `GET /api/parts` - filters: `family`, `manufacturer`, `package`,
  `lifecycle_status` (comma separated), `in_stock`, `q`, `limit`, `offset`.
* `GET /api/parts/{part_id}` - the part with every value, offer and source.
* `GET /api/parts/{part_id}/sources/{param_id}` - the value plus its
  `SourceRef`, the page URL and the page text.
* `GET /api/sources/{source_id}/page/{n}` - `format=meta` (default) returns
  the `SourcePage` JSON, `format=image` returns the rendered PNG.
* `POST /api/search` - a natural-language query. When a `filter` is in the
  body the LLM is **not** called (`llm_used` is then `false`).
* `GET /api/parts/{part_id}/alternatives` - a ranked list.
* `POST /api/bom/check` - multipart (`file`) **or** JSON (`content`).
* `GET /api/review`, `POST /api/review/{param_id}` - the review queue.
* `POST /api/jobs/extract` - **202** with the job, the work runs in the
  background.
* `GET /api/jobs/{job_id}` - the progress.
* `GET /api/stats` - the dashboard numbers.

## 5. The rules the API enforces

* **CORS** - only the origins in `Settings.cors_origins`; the frontend dev
  server. `allow_credentials=False`.
* **Rate limit** - `POST /api/search` uses the LLM, so it is rate limited to
  `Settings.search_rate_limit_per_minute` per client IP. A 429 carries a
  `Retry-After` header.
* **Upload size** - the BOM upload is limited to `Settings.max_upload_bytes`
  (5 MiB). A bigger upload is a 413.
* **Validation** - every input is validated with Pydantic. A bad body, a bad
  query parameter and a body that is not valid JSON are all a **422**, so
  the client has one status to handle. The 422 is documented in the contract
  for every endpoint that can return it.
* **Errors** - always `{"detail": "..."}`. No stack trace, no secret and no
  internal path ever reaches the client.

## 6. The contract test

`tests/api/test_contract.py` does two things:

1. It compares the generated schema with `contracts/openapi.yaml`: the same
   paths, the same operation ids, the same response field names and the same
   parameter bounds.
2. It runs **Schemathesis** against the frozen contract. Schemathesis
   generates requests from the contract and checks that the responses match
   the schema, in both directions: a schema-valid request has to be accepted
   and a schema-violating request has to be rejected.

One hook is needed. A JSON schema cannot say "a CSV with an MPN column", so
Schemathesis generates random text for the BOM upload. The `before_call` hook
replaces it with a real BOM, which makes the positive check meaningful. The
negative check is untouched: a body that violates the schema is still
rejected.

## 7. Known gaps

* The fakes are in-memory. The job registry is not persisted.
* The PDF rendering needs a local PDF; a source without a local file has no
  page to render and the endpoint answers 404.
* `GET /health` is not part of the frozen contract.
* The BOM parser is the service agent's code; this layer only checks the
  size, the content type and the presence of a file.
* The rate limiter is per process. A multi-worker deployment would need a
  shared store.
