"""PartPilot module interfaces (CONTRACT v1).

Every cross-module collaboration in PartPilot goes through the ``typing.Protocol``
classes in this file. Agents implement the protocols; they never import another
agent's package.

The protocols are intentionally *structural*: a class satisfies a protocol by
having the right methods, so a test can pass a hand written fake and a production
code can pass the real implementation without any inheritance.

Rules:
* Method signatures below are FROZEN. Implementations may add keyword-only
  arguments with defaults, but must not change or remove an existing parameter.
* Every implementation must be safe to call without network access when the
  underlying credentials are missing (return empty results or raise a typed
  error, never hang).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from shared.schemas import (
    AlternativeResult,
    BomCheckResponse,
    ExtractionResult,
    Family,
    JobRequest,
    JobStatus,
    LLMCallRecord,
    ParameterValue,
    PartRecord,
    PartSummary,
    ReviewDecision,
    ReviewItem,
    ReviewResponse,
    SearchFilter,
    SearchResponse,
    SourcePage,
    SourceRef,
    StatsResponse,
)

# --------------------------------------------------------------------------------------
# Collectors
# --------------------------------------------------------------------------------------


@runtime_checkable
class Collector(Protocol):
    """Reads part data from one distributor API (plan WP1).

    Implementations must:
    * obey the distributor's published rate limit (see ``shared.config``);
    * cache every raw response to disk with the date, and serve the cache on a
      repeat call so the same part is never requested twice (DigiKey allows
      1000 requests/day);
    * never raise on a single part failure - log the reason and continue.
    """

    name: str

    def search_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return the normalised part for ``mpn`` or ``None`` when not found."""
        ...

    def search_by_keyword(self, keyword: str, limit: int = 25) -> list[PartRecord]:
        """Return normalised parts matching a free-text keyword."""
        ...

    def get_offers(self, mpn: str) -> list[dict[str, Any]]:
        """Return raw distributor offers for ``mpn`` (price breaks, stock)."""
        ...


@runtime_checkable
class DatasheetDownloader(Protocol):
    """Downloads and validates datasheet PDFs (plan WP2, FR-02).

    Implementations must:
    * check ``robots.txt`` for every new host and refuse disallowed paths;
    * send a clear ``User-Agent`` with a contact address;
    * wait at least 1 second between requests to the same host;
    * validate that the body really is a PDF;
    * store the file under a hash-based name and return a :class:`SourceRef`.
    """

    def download(self, url: str, part_id: str | None = None) -> SourceRef | None:
        """Download ``url`` and return its provenance, or ``None`` on failure."""
        ...

    def local_path(self, source_id: str) -> str | None:
        """Return the on-disk path of a previously downloaded source."""
        ...

    def page_count(self, source_id: str) -> int | None:
        """Return the number of pages of a stored PDF."""
        ...

    def is_scanned(self, source_id: str) -> bool:
        """Return ``True`` when the PDF has no text layer (needs Tier 3)."""
        ...


# --------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------


@runtime_checkable
class Tier1Extractor(Protocol):
    """Rule based extraction from a PDF (plan WP3, tier 1).

    Must return one :class:`ExtractionResult` with ``method=TIER1``. Fields that
    cannot be read unambiguously go into ``failed_fields``; they are never
    guessed.
    """

    def extract(self, pdf_path: str, family: Family | None = None) -> ExtractionResult:
        """Extract values from the PDF at ``pdf_path``."""
        ...

    def find_pages(self, pdf_path: str) -> list[int]:
        """Return the 1-based page numbers that hold characteristics tables."""
        ...


@runtime_checkable
class LLMExtractor(Protocol):
    """LLM backed extraction, tiers 2 and 3 (plan WP4).

    Rules:
    * the model is loaded with ``init_chat_model`` from ``shared.config``;
    * every call is wrapped with retry, a rate limiter and a cache;
    * every call is recorded through an injected ``LLMCallRecorder``;
    * the model must never invent a value - a value that is not in the supplied
      text is a failed field, not a guess (NFR-03).
    """

    def extract_tier2(
        self,
        pages: Iterable[tuple[int, str]],
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Tier 2: structured output over page text and table data."""
        ...

    def extract_tier3(
        self,
        page_images: Iterable[tuple[int, bytes]],
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Tier 3: structured output over rendered page images."""
        ...

    def map_name(self, raw_name: str, family: Family) -> str | None:
        """Propose a standard parameter name for an unknown raw name."""
        ...

    def build_search_filter(self, query: str) -> SearchFilter:
        """Turn a natural-language query into a validated filter."""
        ...

    def explain_alternative(self, differences: dict[str, dict[str, float | None]], mpn: str) -> str:
        """Return one short sentence describing the trade-off."""
        ...


@runtime_checkable
class Validator(Protocol):
    """Checks extracted values (plan WP5, FR-06/07/08).

    Must:
    * normalise units with ``pint``;
    * apply a per-field range rule;
    * check ``min <= typ <= max``;
    * cross-check against the API value with a tolerance;
    * compute a confidence from tier + checks + match;
    * set the status to accepted / review / rejected.
    """

    def validate(self, value: ParameterValue, api_value: float | None = None) -> ParameterValue:
        """Return a copy of ``value`` with unit, confidence and status set."""
        ...

    def validate_many(
        self, values: Iterable[ParameterValue], api_values: dict[str, float] | None = None
    ) -> list[ParameterValue]:
        """Validate a batch of values, keyed by standard name for cross-checks."""
        ...

    def normalize(self, value: float | None, unit: str | None) -> tuple[float | None, str | None]:
        """Convert ``value`` to the canonical unit; return ``(value, unit)``."""
        ...


# --------------------------------------------------------------------------------------
# Repository
# --------------------------------------------------------------------------------------


@runtime_checkable
class PartsRepository(Protocol):
    """Persistence for parts, values, sources, offers and reviews (plan section 7)."""

    def add_part(self, part: PartRecord) -> PartRecord:
        """Insert or update a part and its values."""
        ...

    def get_part(self, part_id: str) -> PartRecord | None:
        """Return one part with all values and offers."""
        ...

    def get_part_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return one part looked up by manufacturer part number."""
        ...

    def list_parts(
        self,
        filt: SearchFilter | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PartSummary], int]:
        """Return a page of parts matching ``filt`` and the total match count."""
        ...

    def get_parameters(self, part_id: str) -> list[ParameterValue]:
        """Return every stored value of a part."""
        ...

    def get_parameter(self, param_id: str) -> ParameterValue | None:
        """Return one value by id."""
        ...

    def update_parameter(self, value: ParameterValue) -> ParameterValue:
        """Persist a changed value (validation result or human correction)."""
        ...

    def add_source(self, source: SourceRef) -> SourceRef:
        """Insert or update a source record."""
        ...

    def get_source(self, source_id: str) -> SourceRef | None:
        """Return one source by id."""
        ...

    def get_source_page(self, source_id: str, page: int) -> SourcePage | None:
        """Return one page of a source (text and image reference)."""
        ...

    def add_offer(self, part_id: str, offer: dict[str, Any]) -> None:
        """Store one distributor offer for a part."""
        ...

    def list_review_queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the low-confidence values waiting for review (FR-10)."""
        ...

    def apply_review(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Accept, correct or reject a reviewed value."""
        ...

    def record_llm_call(self, record: LLMCallRecord) -> None:
        """Store one LLM call for cost accounting."""
        ...

    def stats(self) -> StatsResponse:
        """Return dashboard counts and quality numbers."""
        ...


# --------------------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------------------


@runtime_checkable
class SearchService(Protocol):
    """Natural-language and filter search (plan WP6, FR-11)."""

    def search(self, query: str, limit: int = 50, offset: int = 0) -> SearchResponse:
        """Build a filter from ``query`` and execute it against the database."""
        ...

    def search_filter(self, filt: SearchFilter, limit: int = 50, offset: int = 0) -> SearchResponse:
        """Execute an already validated filter."""
        ...


@runtime_checkable
class AlternativesService(Protocol):
    """Ranked alternative parts (FR-13)."""

    def alternatives(
        self, part_id: str, limit: int = 10, explain: bool = True
    ) -> list[AlternativeResult]:
        """Return ranked alternatives for ``part_id``."""
        ...


@runtime_checkable
class BomService(Protocol):
    """BOM health check (FR-14)."""

    def check_csv(self, content: str, filename: str | None = None) -> BomCheckResponse:
        """Parse a BOM CSV and return the risk table."""
        ...


@runtime_checkable
class ReviewService(Protocol):
    """Review queue operations (FR-10)."""

    def queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the review queue."""
        ...

    def decide(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Apply a human decision to one reviewed value."""
        ...


@runtime_checkable
class StatsService(Protocol):
    """Dashboard statistics (plan WP7/WP8)."""

    def stats(self) -> StatsResponse:
        """Return counts and quality numbers."""
        ...


@runtime_checkable
class JobRunner(Protocol):
    """Background extraction jobs (plan WP6, WP2 "do not block a request")."""

    def submit(self, request: JobRequest) -> JobStatus:
        """Queue a job and return its initial status."""
        ...

    def get(self, job_id: str) -> JobStatus | None:
        """Return the current status of a job."""
        ...

    def list(self, limit: int = 50) -> list[JobStatus]:
        """Return recent jobs, newest first."""
        ...


# --------------------------------------------------------------------------------------
# Bundles
# --------------------------------------------------------------------------------------


@runtime_checkable
class CollectorBundle(Protocol):
    """The set of collectors the application uses (FR-01)."""

    collectors: list[Collector]

    def for_family(self, family: Family) -> list[Collector]:
        """Return the collectors that can serve ``family``."""
        ...


__all__ = [
    "AlternativesService",
    "BomService",
    "Collector",
    "CollectorBundle",
    "DatasheetDownloader",
    "JobRunner",
    "LLMExtractor",
    "PartsRepository",
    "ReviewService",
    "SearchService",
    "StatsService",
    "Tier1Extractor",
    "Validator",
]
