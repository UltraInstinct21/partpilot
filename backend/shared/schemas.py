"""PartPilot shared Pydantic schemas (CONTRACT v1).

This module is FROZEN. It is the single source of truth for every payload that
crosses a module boundary (collector -> extractor -> validator -> repository ->
service -> API -> frontend).

Rules encoded here:

* Every stored value carries provenance: ``source_id``, ``page``, ``method``
  (the extraction tier), ``confidence`` and ``condition`` (FR-05, FR-09).
* The LLM must never invent a value. Extraction results therefore only ever
  contain values that a lower tier read from a source; the LLM tier returns
  ``failed_fields`` instead of guessing (NFR-03).
* Units are always SI base units. ``unit`` holds the canonical pint unit
  string, e.g. ``"V"``, ``"A"``, ``"ohm"``, ``"degC"`` (FR-06).

Subagents MUST import from here. They MUST NOT redefine these models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------------------


class Family(str, Enum):
    """Supported component families (plan section 1.2)."""

    MOSFET = "mosfet"
    GATE_DRIVER = "gate_driver"


class SourceType(str, Enum):
    """Kind of source a value was read from (plan section 7, ``sources.type``)."""

    API = "api"
    PDF = "pdf"
    MANUAL = "manual"


class ExtractionMethod(str, Enum):
    """Which extraction tier produced a value (plan section 5.1).

    ``API`` marks a value that came straight from a distributor API and was not
    read from a datasheet. ``MANUAL`` marks a value a person corrected in the
    review queue.
    """

    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"
    API = "api"
    MANUAL = "manual"


class ValueStatus(str, Enum):
    """Validation outcome of a single value (plan section 7, ``parameters.status``)."""

    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"


class LifecycleStatus(str, Enum):
    """Part lifecycle (FR-15)."""

    ACTIVE = "active"
    NRND = "nrnd"
    OBSOLETE = "obsolete"
    UNKNOWN = "unknown"


class JobKind(str, Enum):
    """Background job types (plan WP6)."""

    EXTRACT = "extract"
    COLLECT = "collect"
    SEED = "seed"


class JobState(str, Enum):
    """Background job lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskSeverity(str, Enum):
    """BOM risk severity."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Offer(BaseModel):
    """A distributor offer for a part (plan section 7, ``offers`` table)."""

    model_config = ConfigDict(extra="ignore")

    part_id: str | None = None
    distributor: str
    sku: str | None = None
    stock: int | None = None
    unit_price: float | None = None
    currency: str = "USD"
    price_breaks: list[dict[str, Any]] = Field(default_factory=list)
    lead_time_days: int | None = None
    fetched_at: datetime | None = None
    url: str | None = None


# --------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------


class SourceRef(BaseModel):
    """Provenance record for one fetched artefact (plan section 7, ``sources``)."""

    model_config = ConfigDict(extra="ignore")

    source_id: str
    url: str
    type: SourceType = SourceType.API
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    file_hash: str | None = None
    distributor: str | None = None
    page_count: int | None = None
    local_path: str | None = None
    content_type: str | None = None
    note: str | None = None


class SourcePage(BaseModel):
    """One page of a PDF source, used by the source viewer (FR-12)."""

    model_config = ConfigDict(extra="ignore")

    source_id: str
    page: int
    width: int | None = None
    height: int | None = None
    text: str | None = None
    image_url: str | None = None
    is_image_only: bool = False


# --------------------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------------------


class ParameterValue(BaseModel):
    """One extracted/validated parameter with full provenance (FR-05, FR-09)."""

    model_config = ConfigDict(extra="ignore")

    param_id: str | None = None
    part_id: str | None = None
    name: str
    value: float | None = None
    value_min: float | None = None
    value_typ: float | None = None
    value_max: float | None = None
    unit: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None
    page: int | None = None
    method: ExtractionMethod | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: ValueStatus = ValueStatus.REVIEW
    raw_text: str | None = None
    value_text: str | None = None

    @field_validator("condition", mode="before")
    @classmethod
    def _coerce_condition(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        if isinstance(v, dict):
            return {str(k): v[k] for k in v}
        return {"text": str(v)}

    def representative(self) -> float | None:
        """Return the value used for comparisons: typical > max > min > value."""
        for candidate in (self.value_typ, self.value, self.value_max, self.value_min):
            if candidate is not None:
                return candidate
        return None


class PartSummary(BaseModel):
    """Compact part representation used in lists, search results and tables."""

    model_config = ConfigDict(extra="ignore")

    part_id: str
    mpn: str
    manufacturer: str
    family: Family
    package: str | None = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.UNKNOWN
    datasheet_url: str | None = None
    description: str | None = None
    key_parameters: dict[str, float | None] = Field(default_factory=dict)
    offers_count: int = 0
    total_stock: int | None = None
    score: float | None = None


class PartRecord(BaseModel):
    """A part with all of its values (plan section 7, ``parts`` + ``parameters``)."""

    model_config = ConfigDict(extra="ignore")

    part_id: str
    mpn: str
    manufacturer: str
    family: Family
    package: str | None = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.UNKNOWN
    datasheet_url: str | None = None
    description: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    parameters: list[ParameterValue] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)
    updated_at: datetime | None = None

    def accepted_parameters(self) -> list[ParameterValue]:
        return [p for p in self.parameters if p.status == ValueStatus.ACCEPTED]


# --------------------------------------------------------------------------------------
# Family specifications (LLM structured-output targets, plan section 7.1)
# --------------------------------------------------------------------------------------


class SpecValue(BaseModel):
    """A single specification slot.

    ``value`` is the canonical numeric value in ``unit``. ``condition`` holds the
    test condition (e.g. ``{"vgs": "10 V", "temp": "25 C"}``) - FR-05 requires
    the condition to travel with the value. ``page`` is the datasheet page.
    """

    model_config = ConfigDict(extra="ignore")

    value: float | None = None
    unit: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    page: int | None = None
    raw_text: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_id: str | None = None


class MosfetSpec(BaseModel):
    """Power MOSFET specification (plan section 7.1) - 13 fields."""

    model_config = ConfigDict(extra="ignore")

    vds_max: SpecValue | None = None
    id_continuous: SpecValue | None = None
    rds_on: SpecValue | None = None
    vgs_threshold: SpecValue | None = None
    vgs_max: SpecValue | None = None
    total_gate_charge_qg: SpecValue | None = None
    gate_drain_charge_qgd: SpecValue | None = None
    input_capacitance_ciss: SpecValue | None = None
    output_capacitance_coss: SpecValue | None = None
    max_junction_temp: SpecValue | None = None
    package: SpecValue | None = None
    thermal_resistance: SpecValue | None = None
    reverse_recovery_qrr: SpecValue | None = None


class GateDriverSpec(BaseModel):
    """Gate driver specification (plan section 7.1) - 12 fields."""

    model_config = ConfigDict(extra="ignore")

    supply_voltage_min: SpecValue | None = None
    supply_voltage_max: SpecValue | None = None
    peak_source_current: SpecValue | None = None
    peak_sink_current: SpecValue | None = None
    input_logic_level: SpecValue | None = None
    propagation_delay: SpecValue | None = None
    rise_time: SpecValue | None = None
    fall_time: SpecValue | None = None
    uvlo_threshold: SpecValue | None = None
    channel_count: SpecValue | None = None
    package: SpecValue | None = None
    operating_temp_min: SpecValue | None = None
    operating_temp_max: SpecValue | None = None


SpecSchema = MosfetSpec | GateDriverSpec


# --------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Output of a tier-1/2/3 extraction run."""

    model_config = ConfigDict(extra="ignore")

    part_id: str | None = None
    family: Family | None = None
    method: ExtractionMethod
    source_id: str | None = None
    values: list[ParameterValue] = Field(default_factory=list)
    pages_used: list[int] = Field(default_factory=list)
    failed_fields: list[str] = Field(default_factory=list)
    scanned: bool = False
    notes: str | None = None
    duration_ms: int | None = None

    def failed_names(self) -> set[str]:
        return {f for f in self.failed_fields if f}


# --------------------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------------------


def _strict_int(value: Any) -> Any:
    """Prepare a number for a strict integer field.

    JSON Schema calls ``128.0`` an integer, so the API accepts it, but a
    boolean is not a number and must never be silently read as ``0`` or
    ``1``. Pydantic in strict mode would reject ``128.0`` as well, so an
    integral float is converted first.
    """
    if isinstance(value, bool):
        raise ValueError("a boolean is not a valid number")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class ParameterConstraint(BaseModel):
    """A numeric constraint on one standard parameter name."""

    model_config = ConfigDict(extra="ignore")

    name: str
    unit: str | None = None
    min: float | None = Field(default=None, strict=True)
    max: float | None = Field(default=None, strict=True)
    typ: float | None = Field(default=None, strict=True)
    operator: Literal["lt", "lte", "gt", "gte", "eq", "between"] = "between"

    def bounds(self) -> tuple[float | None, float | None]:
        """Return (lower, upper) implied by the operator."""
        if self.operator == "lt":
            return (None, self.max if self.max is not None else self.typ)
        if self.operator == "lte":
            return (None, self.max if self.max is not None else self.typ)
        if self.operator == "gt":
            return (self.min if self.min is not None else self.typ, None)
        if self.operator == "gte":
            return (self.min if self.min is not None else self.typ, None)
        if self.operator == "eq":
            return (
                self.typ if self.typ is not None else self.min,
                self.typ if self.typ is not None else self.max,
            )
        return (self.min, self.max)


class SearchFilter(BaseModel):
    """A validated, database-executable filter.

    The LLM only ever *builds* this structure. The database always *executes* it
    (plan WP6, "The LLM must not choose the results").
    """

    model_config = ConfigDict(extra="ignore")

    family: Family | None = None
    manufacturer: str | None = None
    manufacturer_in: list[str] = Field(default_factory=list)
    mpn_contains: str | None = None
    package: str | None = None
    package_in: list[str] = Field(default_factory=list)
    lifecycle_status: list[LifecycleStatus] = Field(default_factory=list)
    in_stock: bool | None = Field(default=None, strict=True)
    parameters: list[ParameterConstraint] = Field(default_factory=list)
    text: str | None = None


class SearchRequest(BaseModel):
    """Body of ``POST /api/search``.

    The numbers are strict: a JSON ``false`` is not a valid ``offset``. The
    contract says ``offset`` is an integer, and a silent coercion of a boolean
    into zero would return the wrong page.
    """

    model_config = ConfigDict(extra="ignore")

    query: str = Field(min_length=1, description="The natural-language query.")
    filter: SearchFilter | None = None
    limit: int = Field(default=50, ge=1, le=500, strict=True)
    offset: int = Field(default=0, ge=0, strict=True)

    @field_validator("limit", "offset", mode="before")
    @classmethod
    def _reject_boolean(cls, v: Any) -> Any:
        return _strict_int(v)


class SearchResponse(BaseModel):
    """Result of ``POST /api/search`` and ``GET /api/parts``."""

    model_config = ConfigDict(extra="ignore")

    query: str | None = None
    filter: SearchFilter = Field(default_factory=SearchFilter)
    results: list[PartSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    took_ms: int = 0
    filter_explanation: str | None = None
    llm_used: bool = False


# --------------------------------------------------------------------------------------
# Alternatives
# --------------------------------------------------------------------------------------


class AlternativeResult(BaseModel):
    """One ranked alternative part (FR-13)."""

    model_config = ConfigDict(extra="ignore")

    part: PartSummary
    score: float = 0.0
    rank: int = 0
    reason: str = ""
    rejected: bool = False
    rejection_reason: str | None = None
    differences: dict[str, dict[str, float | None]] = Field(default_factory=dict)


# --------------------------------------------------------------------------------------
# BOM
# --------------------------------------------------------------------------------------


class BomLine(BaseModel):
    """One row of an uploaded BOM CSV."""

    model_config = ConfigDict(extra="ignore")

    line_number: int
    mpn: str
    quantity: int = 1
    manufacturer: str | None = None
    reference: str | None = None
    matched_part_id: str | None = None
    matched: bool = False
    risks: list[BomRisk] = Field(default_factory=list)


class BomRisk(BaseModel):
    """A risk flag raised for a BOM line (FR-14)."""

    model_config = ConfigDict(extra="ignore")

    code: str
    severity: RiskSeverity = RiskSeverity.MEDIUM
    message: str
    part_id: str | None = None
    mpn: str | None = None
    suggestion: str | None = None


class BomCheckRequest(BaseModel):
    """Body of ``POST /api/bom/check`` (also used for the multipart upload)."""

    model_config = ConfigDict(extra="ignore")

    filename: str | None = None
    content: str | None = None


class BomCheckResponse(BaseModel):
    """Result of ``POST /api/bom/check``."""

    model_config = ConfigDict(extra="ignore")

    filename: str | None = None
    total_lines: int = 0
    matched_lines: int = 0
    unmatched_lines: int = 0
    risk_count: int = 0
    highest_severity: RiskSeverity | None = None
    lines: list[BomLine] = Field(default_factory=list)
    risks: list[BomRisk] = Field(default_factory=list)
    took_ms: int = 0


# --------------------------------------------------------------------------------------
# Review queue
# --------------------------------------------------------------------------------------


class ReviewItem(BaseModel):
    """One low-confidence value waiting for a person (FR-10)."""

    model_config = ConfigDict(extra="ignore")

    param_id: str
    part_id: str
    mpn: str
    manufacturer: str
    family: Family
    name: str
    value: float | None = None
    value_min: float | None = None
    value_typ: float | None = None
    value_max: float | None = None
    unit: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None
    page: int | None = None
    method: ExtractionMethod | None = None
    confidence: float = 0.0
    status: ValueStatus = ValueStatus.REVIEW
    reasons: list[str] = Field(default_factory=list)
    raw_text: str | None = None
    created_at: datetime | None = None


class ReviewDecision(BaseModel):
    """Body of ``POST /api/review/{param_id}``."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["accept", "correct", "reject"] = "accept"
    value: float | None = Field(default=None, strict=True)
    value_min: float | None = Field(default=None, strict=True)
    value_typ: float | None = Field(default=None, strict=True)
    value_max: float | None = Field(default=None, strict=True)
    unit: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class ReviewResponse(BaseModel):
    """Result of a review decision."""

    model_config = ConfigDict(extra="ignore")

    param_id: str
    status: ValueStatus
    message: str = ""
    item: ReviewItem | None = None


# --------------------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------------------


class JobStatus(BaseModel):
    """Progress of a background job (plan WP6)."""

    model_config = ConfigDict(extra="ignore")

    job_id: str
    kind: JobKind = JobKind.EXTRACT
    state: JobState = JobState.QUEUED
    progress: int = 0
    total: int = 0
    message: str = ""
    part_id: str | None = None
    source_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobRequest(BaseModel):
    """Body of ``POST /api/jobs/extract``."""

    model_config = ConfigDict(extra="ignore")

    part_id: str | None = None
    source_id: str | None = None
    pdf_path: str | None = None
    family: Family | None = None
    force_tier: Literal[1, 2, 3] | None = None


# --------------------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------------------


class StatsResponse(BaseModel):
    """Counts and quality numbers for the dashboard (plan WP7/WP8)."""

    model_config = ConfigDict(extra="ignore")

    parts_total: int = 0
    parts_by_family: dict[str, int] = Field(default_factory=dict)
    parts_by_lifecycle: dict[str, int] = Field(default_factory=dict)
    parts_by_manufacturer: dict[str, int] = Field(default_factory=dict)
    parameters_total: int = 0
    values_by_status: dict[str, int] = Field(default_factory=dict)
    values_by_method: dict[str, int] = Field(default_factory=dict)
    review_pending: int = 0
    sources_total: int = 0
    coverage_pct: float = 0.0
    mean_confidence: float = 0.0
    llm_calls_total: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    llm_cost_total: float = 0.0
    avg_cost_per_datasheet: float = 0.0
    accuracy: dict[str, float] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --------------------------------------------------------------------------------------
# LLM bookkeeping
# --------------------------------------------------------------------------------------


class LLMCallRecord(BaseModel):
    """One row of the ``llm_calls`` table (plan section 7)."""

    model_config = ConfigDict(extra="ignore")

    call_id: str | None = None
    chain: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    prompt_version: str = ""
    part_id: str | None = None
    cached: bool = False
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LLMCallRecorder(Protocol):  # type: ignore[name-defined]
    """Records every LLM call for cost accounting (NFR-05)."""

    def record(self, record: LLMCallRecord) -> None: ...


# ``Protocol`` is only needed for the recorder hint above; it is imported at the
# top of the module with the other typing helpers.

BomLine.model_rebuild()


__all__ = [
    "AlternativeResult",
    "BomCheckRequest",
    "BomCheckResponse",
    "BomLine",
    "BomRisk",
    "ExtractionMethod",
    "ExtractionResult",
    "Family",
    "GateDriverSpec",
    "JobKind",
    "JobRequest",
    "JobState",
    "JobStatus",
    "LLMCallRecord",
    "LLMCallRecorder",
    "LifecycleStatus",
    "MosfetSpec",
    "Offer",
    "ParameterConstraint",
    "ParameterValue",
    "PartRecord",
    "PartSummary",
    "ReviewDecision",
    "ReviewItem",
    "ReviewResponse",
    "RiskSeverity",
    "SearchFilter",
    "SearchRequest",
    "SearchResponse",
    "SourcePage",
    "SourceRef",
    "SourceType",
    "SpecValue",
    "StatsResponse",
    "ValueStatus",
]
