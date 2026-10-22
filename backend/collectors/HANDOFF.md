# HANDOFF - collection layer (agent A)

Plan **WP1** (API collection) and **WP2** (datasheet download), plan FR-01,
FR-02 and NFR-01, ethics plan section 12.

Everything in this folder was written by agent A. The frozen contract layer
(`backend/shared/*`) was only read, never edited.

---

## 1. What exists

| File | Content |
| --- | --- |
| `collectors/base.py` | `RateLimiter`, `DiskCache`, `CacheStats`, `RetryPolicy`, `TokenCache`, the httpx client factory, the retry helper and the typed errors. |
| `collectors/params.py` | The vendor label -> standard parameter name table, the unit canonicalisation, the condition parser and the family guesser. |
| `collectors/digikey.py` | `DigiKeyCollector` - DigiKey Product Information v4. |
| `collectors/nexar.py` | `NexarCollector` - Nexar (Octopart) supply GraphQL. |
| `collectors/mouser.py` | `MouserCollector` - Mouser Search API (v1 + v2). |
| `collectors/datasheets.py` | `DatasheetDownloader` - robots aware PDF download and validation. |
| `collectors/seeds.py` | `build_seed_list()`, `load_bundled_seed()`, `bundled_part_records()`. |
| `collectors/bundle.py` | `DefaultCollectorBundle` - the `CollectorBundle` protocol. |
| `collectors/manual/collect_manual.py` | Manual script with real credentials (never executed by the test suite). |
| `tests/collectors/` | 119 tests, all HTTP mocked with `respx`. |

## 2. How to run

```bash
cd /home/sarthi/Projects/partpilot-wt/a-collectors/backend
.venv/bin/python -m pytest -q          # 119 passed
.venv/bin/python -m ruff check .       # clean
.venv/bin/python -m black --check .    # clean
```

Manual run (real APIs, needs the credentials in `.env`):

```bash
cd backend
.venv/bin/python -m collectors.manual.collect_manual --dry-run
.venv/bin/python -m collectors.manual.collect_manual --family mosfet --limit 25
.venv/bin/python -m collectors.manual.collect_manual --mpn IRF3205S --datasheets
```

## 3. The public API

### `collectors.base`

```python
class RateLimiter:
    def __init__(self, name: str, per_minute: int, per_day: int, *,
                 clock=time.monotonic, today=None, sleep=time.sleep) -> None
    def acquire(self, *, block: bool = False) -> None   # raises RateLimitExceededError
    def try_acquire(self) -> bool
    def reset(self) -> None
    @property used_minute: int
    @property used_day: int
    @property blocked: int

class DiskCache:
    def __init__(self, root: Path | str, namespace: str = "default", *, clock=None) -> None
    def get(self, key: str) -> Any | None            # a hit makes no HTTP call
    def put(self, key: str, payload: Any) -> Path    # <root>/<ns>/<YYYY-MM-DD>/<sha256>.json
    def stats(self) -> CacheStats                    # .hits .misses .puts .hit_rate
    def path_for(self, key: str, when=None) -> Path
    def hash_key(self, key: str) -> str
    def dated_dirs(self) -> list[Path]
    def clear(self) -> None

@dataclass
class CacheStats: hits: int; misses: int; puts: int; hit_rate: float; as_dict() -> dict

@dataclass
class RetryPolicy:
    max_attempts: int; backoff: float; max_backoff: float; sleep: Callable | None
    @classmethod from_settings(cls, settings=None, *, sleep=None) -> RetryPolicy
    def run(self, func) -> Any
    async def run_async(self, func) -> Any

class TokenCache:
    def __init__(self, *, refresh_margin: float = 60.0, clock=time.monotonic)
    @property token: str | None      # None when it has to be refreshed
    def set(self, token: str, expires_in: float) -> None
    def clear(self) -> None

def make_client(settings=None, **overrides) -> httpx.Client
def make_async_client(settings=None, **overrides) -> httpx.AsyncClient
def request_with_retry(policy, client, method, url, **kwargs) -> httpx.Response
def run_sync(coro) -> Any            # sync facade of the async clients
def user_agent(settings=None) -> str
def status_to_error(response: httpx.Response) -> None

# Errors (all inherit CollectorError)
CollectorError, MissingCredentialsError, RateLimitExceededError,
RetryableStatusError(status_code), HttpStatusError(status_code),
RobotsDisallowedError, InvalidPdfError
```

### `collectors.digikey` / `collectors.nexar` / `collectors.mouser`

Every client implements the frozen `shared.interfaces.Collector` protocol:

```python
name: str                                        # "digikey" | "nexar" | "mouser"
def search_by_mpn(self, mpn: str) -> PartRecord | None
def search_by_keyword(self, keyword: str, limit: int = 25) -> list[PartRecord]
def get_offers(self, mpn: str) -> list[dict[str, Any]]
```

Every client also has the asynchronous twin (`search_by_mpn_async`,
`search_by_keyword_async`, `get_offers_async`) and the constructor

```python
DigiKeyCollector(settings=None, *, client=None, cache=None, limiter=None, retry=None)
NexarCollector(settings=None, *, client=None, cache=None, limiter=None, retry=None)
MouserCollector(settings=None, *, client=None, cache=None, limiter=None, retry=None)
```

`client` is an `httpx.AsyncClient` (injected in the tests), `cache` a
`DiskCache`, `limiter` a `RateLimiter` and `retry` a `RetryPolicy`.

DigiKey only: `fetch_product_details`, `fetch_pricing`, `fetch_media`,
`fetch_substitutions`, `search_keyword`, `search_categories`,
`normalize_product`, `parse_offers`.

Nexar only: `search_mpn`, `search_keyword`, `multi_match`, `parts_by_id`,
`categories`, `manufacturers`, `normalize_part`, `graphql`.

Mouser only: `search_part_number`, `search_keyword`,
`search_part_number_and_manufacturer`, `manufacturer_list`, `normalize_part`,
plus the module function `parse_bool(value) -> bool | None`.

### `collectors.datasheets`

```python
class DatasheetDownloader:
    def __init__(self, settings=None, *, client=None, retry=None,
                 sleep=None, clock=None)
    def download(self, url: str, part_id: str | None = None) -> SourceRef | None
    def local_path(self, source_id: str) -> str | None
    def page_count(self, source_id: str) -> int | None
    def is_scanned(self, source_id: str) -> bool
    async def download_async(self, url, part_id=None) -> SourceRef | None
    async def is_allowed(self, url) -> tuple[bool, str]
    def group_by_hash(self, sources: list[SourceRef]) -> dict[str, list[SourceRef]]
```

`source_id` is `pdf-<sha256 of the content>`, the file is
`<pdf_dir>/<sha256>.pdf`. Two parts with the same datasheet therefore get
the same `source_id`.

### `collectors.seeds`

```python
def build_seed_list(family: Family | str, limit: int = 25, *,
                    collector=None, settings=None) -> list[str]
def load_bundled_seed(family=None, *, settings=None) -> list[str]
def load_bundled_parts(family=None, *, settings=None) -> list[dict]
def bundled_part_records(family=None, *, settings=None) -> list[PartRecord]
FAMILY_KEYWORDS: dict[Family, str]
```

### `collectors.bundle`

```python
class DefaultCollectorBundle:
    def __init__(self, settings=None, collectors=None)
    collectors: list[Collector]
    def for_family(self, family: Family) -> list[Collector]
FAMILY_COLLECTORS: dict[Family, tuple[str, ...]]
```

MOSFET -> DigiKey + Nexar, gate driver -> DigiKey + Mouser + Nexar (the
same split as the seed data).

### `collectors.params`

```python
def resolve_parameter_name(label: str | None, *, allow_fuzzy: bool = False,
                           fuzzy_threshold: int = 95) -> str | None
def parse_value_with_unit(text: str | None) -> tuple[float | None, str | None]
def canonical_unit(unit: str | None) -> str | None
def parse_condition(label: str | None) -> dict[str, str]
def infer_family(*texts) -> str | None
def slugify(text: str) -> str
ALIASES, SHORTNAME_ALIASES, UNIT_ALIASES, CONDITION_KEYS
MOSFET_PARAMS, GATE_DRIVER_PARAMS, STANDARD_PARAMS
```

## 4. The ethics rules that are implemented

1. **Official API first** - only the DigiKey, Nexar and Mouser APIs are used.
   No distributor web page is scraped.
2. **robots.txt per host** - fetched once per host and cached for the
   session. A disallowed path is refused, the request is never sent
   (`test_a_disallowed_path_is_refused_and_never_requested`). A missing
   robots.txt (404) allows the download, an unreadable one refuses the host.
3. **Clear User-Agent** - `Settings.user_agent` (contains a contact
   address) is sent on every request.
4. **One second between two requests to one host** -
   `Settings.download_delay_seconds`; the sleep and the clock are injectable
   so the test is fast.
5. **Everything is cached with the date** -
   `data/raw/<collector>/<YYYY-MM-DD>/<sha256>.json`. A cache hit makes no
   request at all (also across days, the older dated directories are
   searched).
6. **No bot protection is bypassed** - a login page or a CAPTCHA is an HTML
   body and is rejected by the PDF check.
7. **No datasheet is committed** - the PDFs land in `data/` (git-ignored).
   Only the hash, the URL and the page count are stored.
8. **Rate limits** - DigiKey 60/min + 800/day, Mouser 20/min + 800/day,
   Nexar 60/min + 800/day (`Settings`). The limiter raises
   `RateLimitExceededError` before the budget is exceeded.
9. **No secret is logged or cached** - the OAuth tokens are never written to
   the disk cache; the Mouser API key is redacted in the `httpx` log
   (`_ApiKeyRedactingFilter`) and never part of a cache key.

## 5. Assumptions about the frozen contracts

* **The `Collector` protocol is synchronous.** The clients are asynchronous
  inside (httpx `AsyncClient`) and expose the synchronous protocol methods
  through `run_sync()`. `run_sync()` also works when the caller already
  runs inside an event loop (the coroutine is then executed in a worker
  thread). The asynchronous twins (`*_async`) are public as well.
* **`PartRecord.part_id`** is `<family>-<slug of the mpn>`
  (`mosfet-irf3205s`, `gate-driver-ucc27511`) and the `source_id` of an API
  value is `api-<collector>-<slug>` (`api-digikey-irf3205s`). Both follow
  the naming of `contracts/fixtures/seed/parts.json`.
* **`method=ExtractionMethod.API`** and `confidence=0.90` for every value
  that comes from an API (the contract's confidence model gives 0.90 for
  the method `api`). `status` stays `review` - the validator (agent D) sets
  the final status.
* **`condition`** is parsed out of the vendor label:
  `"RDS(on) @ Id, Vgs"` -> `{"Id": "specified", "Vgs": "specified"}`,
  `"Continuous Drain Current (Id) @ 25°C"` -> `{"Tc": "25 C"}`. A condition
  without a number is marked `"specified"` because the number is only in
  the datasheet (FR-05).
* **Unknown labels map to `None`.** A value is never attached to a name
  that was only guessed (rule 5 / NFR-03). The fuzzy match
  (`allow_fuzzy=True`, score >= 95) is available but off by default - the
  tier-2 name mapper has to approve a mapping first.
* **`package`** is a text parameter: `PartRecord.package` holds the string
  (`TO-220AB`) and the parameter value stays `None` (as in the seed data).
* **A family that cannot be determined** falls back to `mosfet` and logs a
  warning; `PartRecord.family` is a required field with only two members.
* **`SourceRef.local_path`** holds the absolute path of the PDF,
  `file_hash` the sha256 of the content, `distributor` the host of the
  datasheet and `note` the `part_id` that was passed in.
* **A missing credential** raises `MissingCredentialsError` (a typed
  error, allowed by the interface contract) instead of hanging or
  returning a wrong answer.

## 6. Known gaps and open points

1. **No real API call has been made.** Every test is hermetic. The real
   endpoints and the exact JSON shapes of DigiKey v4, Nexar and Mouser were
   taken from `docs/CONTRACTS.md` and the recorded fixtures; a live run may
   need small field adjustments (for example the exact body of the DigiKey
   keyword search or the `CategoryIds` filter).
2. **The category search of the seed builder is thin.** `build_seed_list()`
   asks the collector for a keyword search of the family. The plan wants a
   *category* search; `DigiKeyCollector.search_categories()` exists and
   returns the raw category document, but the builder does not yet walk
   the category tree (that would cost requests - see the DigiKey budget).
3. **`RobotsDisallowedError` and `InvalidPdfError` are never raised.**
   `download()` logs the reason and returns `None` (the interface asks for
   that). The two errors exist for a caller that wants to fail hard.
4. **The Nexar `specs` array** contains one row per variant. The first row
   with a number wins; a row without a number is skipped. A real part with
   several variants would need the variant (package) to be taken into
   account - that is left to the validator.
5. **No datasheet is downloaded for the fixtures** - the fixture URLs point
   to `example.invalid`. The downloader is tested with the synthetic PDFs
   of `contracts/fixtures/pdfs/`.
6. **The Mouser fixture carries MOSFET attributes for gate drivers** (the
   fixture is synthetic). The labels are mapped as they are; the family
   comes from the category. No value is invented and no label is dropped.
7. **`collectors.manual` is missing in `backend/pyproject.toml`** - see
   `docs/CHANGE_REQUESTS/a-collectors-1.md`. The script runs from the
   repository, so nothing is blocked.
8. **No part is written to the database.** The repository is agent E's
   folder; the collectors return `PartRecord` objects and let the caller
   store them.
9. **The disk cache has no eviction.** The raw directory grows with every
   request. A housekeeping job (delete the raw files of a day that is older
   than N days) is still missing.

## 7. How the next agent uses this

```python
from collectors import (
    DefaultCollectorBundle, DigiKeyCollector, DatasheetDownloader,
    build_seed_list, load_bundled_seed,
)

bundle = DefaultCollectorBundle(settings)
record = bundle.for_family(Family.MOSFET)[0].search_by_mpn("IRF3205S")
source = DatasheetDownloader(settings).download(record.datasheet_url, record.part_id)
```

Everything is server side: the browser never calls a distributor API and
never sees a key (NFR-02, NFR-07).
