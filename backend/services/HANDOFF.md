# HANDOFF - Agent F (services)

Plan **WP6** (services), **FR-11** (search), **FR-13** (alternatives),
**FR-14** (BOM check). Branch: `agent/f-services`.

Everything in `backend/services/` is implemented against the **frozen**
contracts in `backend/shared/interfaces.py` and `backend/shared/schemas.py`.
No other agent's package is imported - every collaborator is injected.

---

## 1. What exists

| File | Public class / function | Protocol it satisfies |
| --- | --- | --- |
| `backend/services/search.py` | `SearchService`, `describe_filter(filt)`, `validate_filter(filt)` | `interfaces.SearchService` |
| `backend/services/alternatives.py` | `AlternativesService` | `interfaces.AlternativesService` |
| `backend/services/bom.py` | `BomService` | `interfaces.BomService` |
| `backend/services/review.py` | `ReviewService` | `interfaces.ReviewService` |
| `backend/services/stats.py` | `StatsService` | `interfaces.StatsService` |
| `backend/services/jobs.py` | `BackgroundJobRunner` | `interfaces.JobRunner` |
| `backend/services/__init__.py` | re-exports all of the above | - |
| `backend/tests/services/fakes.py` | `FakePartsRepository`, `FakeLLMExtractor`, `FakeTier1Extractor`, `FakeValidator`, `make_part`, `load_seed_parts`, `synthesize_offers` | test doubles |

Tests: `backend/tests/services/test_search.py`, `test_alternatives.py`,
`test_bom.py`, `test_review.py`, `test_stats.py`, `test_jobs.py`,
`test_contracts.py` - **73 test cases** (72 service cases + 1 protocol check).

> The fakes live in the **test tree** on purpose. The API agent copies
> `backend/tests/services/fakes.py` into its own branch (agents must not
> import another agent's package).

---

## 2. Public API and constructor signatures (for the DI container)

```python
from services import (
    AlternativesService,
    BackgroundJobRunner,
    BomService,
    ReviewService,
    SearchService,
    StatsService,
    describe_filter,
)

SearchService(
    repository: PartsRepository,
    llm: LLMExtractor | None = None,
    *,
    max_limit: int = 200,
    max_offset: int = 10_000,
)
# .search(query: str, limit: int = 50, offset: int = 0) -> SearchResponse
# .search_filter(filt: SearchFilter, limit: int = 50, offset: int = 0) -> SearchResponse
# .describe_filter(filt: SearchFilter) -> str

AlternativesService(
    repository: PartsRepository,
    llm: LLMExtractor | None = None,
    *,
    weights: dict[Family, dict[str, float]] | None = None,
    stock_bonus: float = 5.0,
    stock_target: float = 5000.0,
    lifecycle_bonus: float = 5.0,
    max_relative_difference: float = 2.0,
    max_explanations: int = 3,
)
# .alternatives(part_id: str, limit: int = 10, explain: bool = True) -> list[AlternativeResult]
# .explain_alternative(differences: dict, mpn: str) -> str

BomService(
    repository: PartsRepository,
    *,
    low_stock_threshold: int = 1000,
    single_source_max: int = 1,
)
# .check_csv(content: str, filename: str | None = None) -> BomCheckResponse

ReviewService(repository: PartsRepository)
# .queue(limit: int = 50, offset: int = 0) -> list[ReviewItem]
# .decide(param_id: str, decision: ReviewDecision) -> ReviewResponse

StatsService(repository: PartsRepository)
# .stats() -> StatsResponse

BackgroundJobRunner(
    repository: PartsRepository,
    tier1: Tier1Extractor | None = None,
    llm: LLMExtractor | None = None,
    validator: Validator | None = None,
    *,
    background_tasks: Any | None = None,      # FastAPI BackgroundTasks
    pages_provider: Callable[[str], list[tuple[int, str]]] | None = None,
    max_jobs: int = 200,
)
# .submit(request: JobRequest) -> JobStatus          (state=queued, returns immediately)
# .get(job_id: str) -> JobStatus | None
# .list(limit: int = 50) -> list[JobStatus]           (newest first)
# .run_job(job_id: str, request: JobRequest) -> JobStatus   (the background task body)
```

### Wiring example (API agent)

```python
services = Services(
    search=SearchService(repo, llm),
    alternatives=AlternativesService(repo, llm),
    bom=BomService(repo),
    review=ReviewService(repo),
    stats=StatsService(repo),
    jobs=BackgroundJobRunner(repo, tier1, llm, validator, background_tasks=background_tasks),
)
```

`background_tasks` is optional: without it the runner uses a daemon thread.
Pass the FastAPI `BackgroundTasks` object of the request to run the job
*after* the response was sent.

---

## 3. Behaviour that matters for the API layer

### Search (FR-11)

* `search(query)` asks the LLM for a `SearchFilter`, **validates** it and
  executes it with `repository.list_parts(filt, limit, offset)`.
  The LLM never sees or chooses a result row.
* `search_filter(filt)` executes an already built filter - **no LLM call**
  (`llm_used=False`). This is the path for the edited filter chips.
* Validation: a constraint on an unknown parameter name is **dropped**; an
  impossible range (`min > max`) is **repaired** (the bounds are swapped); a
  constraint without any bound is dropped.
  The allowed names are `MOSFET_PARAMETERS` / `GATE_DRIVER_PARAMETERS`
  (`services.search`); when the family is unknown the union is used.
* `limit` is clamped to `1..max_limit` (200), `offset` to `0..max_offset`.
* If the LLM raises, the search falls back to an **empty filter** and answers
  with `llm_used=False`. The request never fails.
* `took_ms` is measured around the whole request; `filter_explanation` is the
  human sentence from `describe_filter()`.

### Alternatives (FR-13)

* Candidates are collected from configured distributor providers first
  (DigiKey, Mouser, Nexar/Octopart, plus configured web scrapers), then
  merged with the indexed catalogue. The indexed catalogue is a cache and
  fallback, not the sole source of alternatives.
* The same-family/same-package rule is applied after provider and catalogue
  candidates are merged. When **no** part of the family uses the reference
  package, the whole family is used (fallback).
* Hard rules -> the candidate is returned with `rejected=True` and a
  `rejection_reason`, ranked **below** the accepted ones:
  `different family`, `obsolete part`, `lower Vds / lower supply voltage than
  the reference`, `different package (reference is ...)`.
* Score: `90 * (1 - weighted relative distance)` + stock bonus (max 5) +
  lifecycle bonus (max 5) -> 0..100. The distance uses the per family weight
  table (`MOSFET_WEIGHTS`, `GATE_DRIVER_WEIGHTS`) and a **relative**
  difference `|candidate - reference| / |reference|`, capped at
  `max_relative_difference` (2.0) so that one field can not dominate.
* `reason` is generated locally from the **two biggest differences**
  ("lower Rds(on), higher Qg"). With `explain=True` **and** an injected LLM
  the reason may be polished, but the polished text is **rejected** when it
  contains a number that is not in the input (rule 5). At most
  `max_explanations` (3) candidates are polished, so the LLM cost stays
  bounded.
* `differences` holds `{"<field>": {"reference": x, "candidate": y}}` for every
  compared field.
* `limit` applies to the accepted list **and** to the rejected list.

### BOM (FR-14)

* The delimiter (`,` `;` tab) and the header are detected. A file without a
  header is read as pure data. The MPN column is found by name
  (`mpn`, `part number`, `manufacturer part number`, ...) and falls back to the
  first column.
* Every line is matched with `get_part_by_mpn` and, if that fails, with
  `list_parts(SearchFilter(mpn_contains=...))`.
* Risk codes and severities:

  | code | severity |
  | --- | --- |
  | `obsolete` | critical |
  | `not_found` | high |
  | `nrnd` | medium |
  | `low_stock` | medium |
  | `manufacturer_mismatch` | medium |
  | `single_source` | low |
  | `unknown_lifecycle` | low |

* `total_lines`, `matched_lines`, `unmatched_lines`, `risk_count`,
  `highest_severity` and `took_ms` are filled in. A broken CSV never raises.

### Jobs

* `submit()` returns a **snapshot** with `state=queued` (the worker may
  already have finished when the caller looks at the registry).
* Pipeline: tier 1 -> (on failure) tier 2 over the page text -> validator ->
  repository. The job ends in `completed` or `failed` (with `error`).
* The registry is **in memory only** - a restart loses the history. The
  progress of a running job is not persisted either.

---

## 4. How to run

```bash
cd /home/sarthi/Projects/partpilot-wt/f-services/backend
.venv/bin/python -m pytest -q          # 92 tests (73 of this agent)
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .
```

No network and no model is used: every test runs against the recorded
fixtures (`contracts/fixtures/seed/parts.json`) and the fakes.

---

## 5. Known gaps and assumptions about the frozen contracts

1. **`PartSummary.key_parameters` must be filled by the repository.**
   `AlternativesService` reads the compared fields from
   `PartSummary.key_parameters` and only falls back to `get_part()` when a
   field is missing. The real repository (agent E) should fill it with the
   key fields of the family (see `services.alternatives.MOSFET_WEIGHTS`).
2. **Units must be canonical per parameter.** The comparison is a relative
   difference of two raw numbers, so `rds_on` has to be stored in the same
   unit for every part. The frozen contract says SI base units; the seed
   fixture uses `mohm` for `rds_on` - the collector/data agents must pick one
   and stick to it (a change request asks for this).
3. **The seed fixture has no offers.** The stock bonus, `low_stock` and
   `single_source` can therefore not be exercised with the real seed. The
   fake synthesises deterministic offers for the seed parts
   (`fakes.synthesize_offers`); the BOM tests use explicit parts.
4. **The job registry is not persisted** (see above). A restart loses the
   running jobs.
5. **Tier 2 needs page text.** The runner reads it with `pdfplumber` when no
   `pages_provider` is injected. The PDF text extraction itself belongs to
   the extraction agents, so the DI container should pass a `pages_provider`
   in production.
6. `SearchFilter.parameters` is validated against a **fixed list of standard
   names**. A new standard parameter has to be added to
   `services.search.MOSFET_PARAMETERS` / `GATE_DRIVER_PARAMETERS`.

## 6. Change requests

* `docs/CHANGE_REQUESTS/f-services-1.md` - the seed fixture has no offer or
  stock data and uses `mohm` where the contract asks for SI base units.
