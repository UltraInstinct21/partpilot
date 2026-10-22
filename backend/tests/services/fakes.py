"""In-memory fakes for the PartPilot contracts.

These fakes live in the **test tree** on purpose: every agent writes its own
copy (agents must not import another agent's package). The API agent may copy
this file into its own branch.

Nothing here touches the network, the file system (except the read only seed
fixture) or a real model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from shared.schemas import (
    ExtractionMethod,
    ExtractionResult,
    Family,
    LifecycleStatus,
    LLMCallRecord,
    Offer,
    ParameterConstraint,
    ParameterValue,
    PartRecord,
    PartSummary,
    ReviewDecision,
    ReviewItem,
    ReviewResponse,
    SearchFilter,
    SourcePage,
    SourceRef,
    StatsResponse,
    ValueStatus,
)

__all__ = [
    "FakeLLMExtractor",
    "FakePartsRepository",
    "FakeTier1Extractor",
    "FakeValidator",
    "load_seed_parts",
    "make_part",
    "synthesize_offers",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_PARTS_PATH = REPO_ROOT / "contracts" / "fixtures" / "seed" / "parts.json"

#: Scale factors used to compare a stored value with a constraint that uses a
#: different (but compatible) unit.
_UNIT_SCALE: dict[str, float] = {
    "V": 1.0,
    "mV": 1e-3,
    "kV": 1e3,
    "A": 1.0,
    "mA": 1e-3,
    "ohm": 1.0,
    "mohm": 1e-3,
    "uohm": 1e-6,
    "kohm": 1e3,
    "W": 1.0,
    "mW": 1e-3,
    "degC": 1.0,
    "C": 1.0,
    "K": 1.0,
    "nC": 1.0,
    "uC": 1e-3,
    "pF": 1.0,
    "nF": 1e-3,
    "uF": 1e-6,
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "ns": 1e-9,
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "J": 1.0,
    "mJ": 1e-3,
    "sec": 1.0,
}


def _scale(value: float, unit: str | None) -> float:
    """Convert ``value`` to the base unit of ``unit``."""
    if unit is None:
        return value
    return value * _UNIT_SCALE.get(unit, 1.0)


def load_seed_parts(path: Path | None = None) -> list[PartRecord]:
    """Load the 30 seed parts from ``contracts/fixtures/seed/parts.json``."""
    source = path or SEED_PARTS_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    parts: list[PartRecord] = []
    for raw in payload["parts"]:
        parameters: list[ParameterValue] = []
        for name, spec in (raw.get("parameters") or {}).items():
            parameters.append(
                ParameterValue(
                    name=name,
                    value=spec.get("value"),
                    unit=spec.get("unit"),
                    condition=spec.get("condition") or {},
                    method=ExtractionMethod.API,
                    confidence=0.9,
                    status=ValueStatus.ACCEPTED,
                )
            )
        parts.append(
            PartRecord(
                part_id=raw["part_id"],
                mpn=raw["mpn"],
                manufacturer=raw["manufacturer"],
                family=Family(raw["family"]),
                package=raw.get("package"),
                lifecycle_status=LifecycleStatus(raw.get("lifecycle_status", "unknown")),
                datasheet_url=raw.get("datasheet_url"),
                description=raw.get("description"),
                source_ids=list(raw.get("source_ids") or []),
                parameters=parameters,
            )
        )
    return parts


def synthesize_offers(part_id: str, count: int | None = None) -> list[Offer]:
    """Return deterministic offers for a part (the seed has no offer data)."""
    digest = hashlib.sha256(part_id.encode("utf-8")).hexdigest()
    distributors = ["digikey", "mouser", "nexar"]
    number = count if count is not None else 1 + int(digest[:2], 16) % 3
    offers: list[Offer] = []
    for index in range(min(number, len(distributors))):
        chunk = digest[2 + 2 * index : 4 + 2 * index]
        stock = 100 + (int(chunk, 16) * 37) % 9000
        offers.append(
            Offer(
                distributor=distributors[index],
                sku=f"{part_id}-{index}",
                stock=stock,
                unit_price=round(0.5 + (int(chunk, 16) % 100) / 10.0, 2),
                currency="USD",
            )
        )
    return offers


def make_part(
    part_id: str,
    mpn: str,
    *,
    manufacturer: str = "Test Manufacturer",
    family: Family = Family.MOSFET,
    package: str | None = "TO-220AB",
    lifecycle: LifecycleStatus = LifecycleStatus.ACTIVE,
    parameters: dict[str, float] | None = None,
    offers: list[Offer] | None = None,
    description: str | None = None,
) -> PartRecord:
    """Build a part with plain values - handy in tests."""
    values = [
        ParameterValue(
            name=name,
            value=value,
            method=ExtractionMethod.API,
            confidence=0.9,
            status=ValueStatus.ACCEPTED,
        )
        for name, value in (parameters or {}).items()
    ]
    return PartRecord(
        part_id=part_id,
        mpn=mpn,
        manufacturer=manufacturer,
        family=family,
        package=package,
        lifecycle_status=lifecycle,
        description=description,
        parameters=values,
        offers=list(offers or []),
    )


class FakePartsRepository:
    """An in-memory :class:`~shared.interfaces.PartsRepository`.

    The filter implementation is real (not a stub) so that the search tests
    are meaningful: the repository really chooses the result rows.

    Every call is recorded in :attr:`calls` so a test can prove that the
    *repository* (and not the LLM) chose the results.
    """

    def __init__(
        self,
        parts: list[PartRecord] | None = None,
        *,
        seed: bool = True,
        with_synthetic_offers: bool = True,
    ) -> None:
        self._parts: dict[str, PartRecord] = {}
        self._sources: dict[str, SourceRef] = {}
        self._pages: dict[tuple[str, int], SourcePage] = {}
        self._llm_calls: list[LLMCallRecord] = []
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        if parts is None and seed:
            loaded = load_seed_parts()
            for part in loaded:
                if with_synthetic_offers:
                    part.offers = synthesize_offers(part.part_id)
                self._store(part)
        elif parts:
            for part in parts:
                self._store(part)

    # -- helpers ----------------------------------------------------------------

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def _store(self, part: PartRecord) -> PartRecord:
        stored = part.model_copy(deep=True)
        for parameter in stored.parameters:
            if parameter.part_id is None:
                parameter.part_id = stored.part_id
            if parameter.param_id is None:
                parameter.param_id = f"{stored.part_id}:{parameter.name}"
        self._parts[stored.part_id] = stored
        return stored

    def calls_to(self, name: str) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        """Return every recorded call of ``name``."""
        return [call for call in self.calls if call[0] == name]

    def last_filter(self) -> SearchFilter | None:
        """Return the filter of the last ``list_parts`` call."""
        for name, args, _kwargs in reversed(self.calls):
            if name == "list_parts" and args:
                filt = args[0]
                if isinstance(filt, SearchFilter):
                    return filt
        return None

    def _total_stock(self, part: PartRecord) -> int:
        return sum(int(offer.stock or 0) for offer in part.offers)

    def _summary(self, part: PartRecord) -> PartSummary:
        key_parameters: dict[str, float | None] = {}
        for parameter in part.parameters:
            key_parameters[parameter.name] = parameter.representative()
        return PartSummary(
            part_id=part.part_id,
            mpn=part.mpn,
            manufacturer=part.manufacturer,
            family=part.family,
            package=part.package,
            lifecycle_status=part.lifecycle_status,
            datasheet_url=part.datasheet_url,
            description=part.description,
            key_parameters=key_parameters,
            offers_count=len(part.offers),
            total_stock=self._total_stock(part) if part.offers else None,
        )

    def _parameter_value(self, part: PartRecord, name: str) -> tuple[float | None, str | None]:
        for parameter in part.parameters:
            if parameter.name == name:
                return parameter.representative(), parameter.unit
        return None, None

    def _matches_constraint(self, part: PartRecord, constraint: ParameterConstraint) -> bool:
        value, unit = self._parameter_value(part, constraint.name)
        if value is None:
            return False
        scaled = _scale(value, unit)
        constraint_unit = constraint.unit or unit
        lower, upper = constraint.bounds()
        operator = constraint.operator
        if operator == "lt":
            if upper is None:
                return True
            return scaled < _scale(upper, constraint_unit)
        if operator == "lte":
            if upper is None:
                return True
            return scaled <= _scale(upper, constraint_unit)
        if operator == "gt":
            if lower is None:
                return True
            return scaled > _scale(lower, constraint_unit)
        if operator == "gte":
            if lower is None:
                return True
            return scaled >= _scale(lower, constraint_unit)
        if operator == "eq":
            target = constraint.typ if constraint.typ is not None else constraint.min
            if target is None:
                return True
            return abs(scaled - _scale(target, constraint_unit)) <= 1e-9
        # between
        if lower is not None and scaled < _scale(lower, constraint_unit):
            return False
        if upper is not None and scaled > _scale(upper, constraint_unit):
            return False
        return True

    def _matches(self, part: PartRecord, filt: SearchFilter | None) -> bool:
        if filt is None:
            return True
        if filt.family is not None and part.family != filt.family:
            return False
        if filt.manufacturer and part.manufacturer.lower() != filt.manufacturer.lower():
            return False
        if filt.manufacturer_in:
            wanted = {item.lower() for item in filt.manufacturer_in}
            if part.manufacturer.lower() not in wanted:
                return False
        if filt.package and part.package != filt.package:
            return False
        if filt.package_in and part.package not in filt.package_in:
            return False
        if filt.lifecycle_status and part.lifecycle_status not in filt.lifecycle_status:
            return False
        if filt.in_stock is not None:
            in_stock = self._total_stock(part) > 0
            if bool(filt.in_stock) != in_stock:
                return False
        if filt.mpn_contains and filt.mpn_contains.lower() not in part.mpn.lower():
            return False
        if filt.text:
            needle = filt.text.lower()
            haystack = " ".join(
                filter(
                    None,
                    [
                        part.mpn,
                        part.manufacturer,
                        part.description,
                        part.package,
                    ],
                )
            ).lower()
            if needle not in haystack:
                return False
        for constraint in filt.parameters:
            if not self._matches_constraint(part, constraint):
                return False
        return True

    def _find_parameter(self, param_id: str) -> tuple[PartRecord, ParameterValue] | None:
        for part in self._parts.values():
            for parameter in part.parameters:
                if parameter.param_id == param_id:
                    return part, parameter
        return None

    def _review_item(self, part: PartRecord, parameter: ParameterValue) -> ReviewItem:
        return ReviewItem(
            param_id=parameter.param_id or f"{part.part_id}:{parameter.name}",
            part_id=part.part_id,
            mpn=part.mpn,
            manufacturer=part.manufacturer,
            family=part.family,
            name=parameter.name,
            value=parameter.value,
            value_min=parameter.value_min,
            value_typ=parameter.value_typ,
            value_max=parameter.value_max,
            unit=parameter.unit,
            condition=dict(parameter.condition),
            source_id=parameter.source_id,
            page=parameter.page,
            method=parameter.method,
            confidence=parameter.confidence,
            status=parameter.status,
            reasons=[],
            raw_text=parameter.raw_text,
        )

    # -- protocol ---------------------------------------------------------------

    def add_part(self, part: PartRecord) -> PartRecord:
        """Insert or update a part and its values."""
        self._record("add_part", part)
        return self._store(part)

    def get_part(self, part_id: str) -> PartRecord | None:
        """Return one part with all values and offers."""
        self._record("get_part", part_id)
        part = self._parts.get(part_id)
        return part.model_copy(deep=True) if part is not None else None

    def get_part_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return one part looked up by manufacturer part number."""
        self._record("get_part_by_mpn", mpn)
        needle = (mpn or "").strip().lower()
        for part in self._parts.values():
            if part.mpn.lower() == needle:
                return part.model_copy(deep=True)
        return None

    def list_parts(
        self,
        filt: SearchFilter | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PartSummary], int]:
        """Return a page of parts matching ``filt`` and the total match count."""
        self._record("list_parts", filt, limit=limit, offset=offset)
        matched = [part for part in self._parts.values() if self._matches(part, filt)]
        total = len(matched)
        start = max(0, int(offset))
        end = start + max(0, int(limit))
        page = matched[start:end]
        return [self._summary(part) for part in page], total

    def get_parameters(self, part_id: str) -> list[ParameterValue]:
        """Return every stored value of a part."""
        self._record("get_parameters", part_id)
        part = self._parts.get(part_id)
        if part is None:
            return []
        return [parameter.model_copy(deep=True) for parameter in part.parameters]

    def get_parameter(self, param_id: str) -> ParameterValue | None:
        """Return one value by id."""
        self._record("get_parameter", param_id)
        found = self._find_parameter(param_id)
        return found[1].model_copy(deep=True) if found else None

    def update_parameter(self, value: ParameterValue) -> ParameterValue:
        """Persist a changed value."""
        self._record("update_parameter", value)
        found = self._find_parameter(value.param_id or "")
        if found is None:
            return value.model_copy(deep=True)
        part, parameter = found
        parameter.value = value.value
        parameter.value_min = value.value_min
        parameter.value_typ = value.value_typ
        parameter.value_max = value.value_max
        parameter.unit = value.unit
        parameter.confidence = value.confidence
        parameter.status = value.status
        parameter.condition = dict(value.condition)
        return parameter.model_copy(deep=True)

    def add_source(self, source: SourceRef) -> SourceRef:
        """Insert or update a source record."""
        self._record("add_source", source)
        self._sources[source.source_id] = source.model_copy(deep=True)
        return source.model_copy(deep=True)

    def get_source(self, source_id: str) -> SourceRef | None:
        """Return one source by id."""
        self._record("get_source", source_id)
        source = self._sources.get(source_id)
        return source.model_copy(deep=True) if source is not None else None

    def get_source_page(self, source_id: str, page: int) -> SourcePage | None:
        """Return one page of a source."""
        self._record("get_source_page", source_id, page)
        found = self._pages.get((source_id, page))
        return found.model_copy(deep=True) if found is not None else None

    def add_offer(self, part_id: str, offer: dict[str, Any]) -> None:
        """Store one distributor offer for a part."""
        self._record("add_offer", part_id, offer)
        part = self._parts.get(part_id)
        if part is None:
            return
        if isinstance(offer, Offer):
            part.offers.append(offer.model_copy(deep=True))
        else:
            part.offers.append(Offer.model_validate(offer))

    def list_review_queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the low-confidence values waiting for review."""
        self._record("list_review_queue", limit=limit, offset=offset)
        items: list[ReviewItem] = []
        for part in self._parts.values():
            for parameter in part.parameters:
                if parameter.status == ValueStatus.REVIEW:
                    items.append(self._review_item(part, parameter))
        start = max(0, int(offset))
        end = start + max(0, int(limit))
        return items[start:end]

    def apply_review(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Accept, correct or reject a reviewed value."""
        self._record("apply_review", param_id, decision)
        found = self._find_parameter(param_id)
        if found is None:
            return ReviewResponse(
                param_id=param_id,
                status=ValueStatus.REVIEW,
                message="unknown parameter",
            )
        part, parameter = found
        if decision.action == "accept":
            parameter.status = ValueStatus.ACCEPTED
            parameter.confidence = 1.0
            parameter.method = ExtractionMethod.MANUAL
            message = "Value accepted."
        elif decision.action == "correct":
            if decision.value is not None:
                parameter.value = decision.value
            if decision.value_min is not None:
                parameter.value_min = decision.value_min
            if decision.value_typ is not None:
                parameter.value_typ = decision.value_typ
            if decision.value_max is not None:
                parameter.value_max = decision.value_max
            if decision.unit is not None:
                parameter.unit = decision.unit
            if decision.condition:
                parameter.condition = dict(decision.condition)
            parameter.status = ValueStatus.ACCEPTED
            parameter.confidence = 1.0
            parameter.method = ExtractionMethod.MANUAL
            message = "Value corrected."
        else:
            parameter.status = ValueStatus.REJECTED
            parameter.confidence = 0.0
            parameter.method = ExtractionMethod.MANUAL
            message = "Value rejected."
        return ReviewResponse(
            param_id=param_id,
            status=parameter.status,
            message=message,
            item=self._review_item(part, parameter),
        )

    def record_llm_call(self, record: LLMCallRecord) -> None:
        """Store one LLM call for cost accounting."""
        self._record("record_llm_call", record)
        self._llm_calls.append(record.model_copy(deep=True))

    def stats(self) -> StatsResponse:
        """Return dashboard counts and quality numbers."""
        self._record("stats")
        parts_by_family: dict[str, int] = {}
        parts_by_lifecycle: dict[str, int] = {}
        parts_by_manufacturer: dict[str, int] = {}
        values_by_status: dict[str, int] = {}
        values_by_method: dict[str, int] = {}
        parameters_total = 0
        review_pending = 0
        confidence_sum = 0.0
        confidence_count = 0
        covered = 0
        for part in self._parts.values():
            parts_by_family[part.family.value] = parts_by_family.get(part.family.value, 0) + 1
            key = part.lifecycle_status.value
            parts_by_lifecycle[key] = parts_by_lifecycle.get(key, 0) + 1
            parts_by_manufacturer[part.manufacturer] = (
                parts_by_manufacturer.get(part.manufacturer, 0) + 1
            )
            accepted = False
            for parameter in part.parameters:
                parameters_total += 1
                status = parameter.status.value
                values_by_status[status] = values_by_status.get(status, 0) + 1
                method = parameter.method.value if parameter.method else "unknown"
                values_by_method[method] = values_by_method.get(method, 0) + 1
                if parameter.status == ValueStatus.REVIEW:
                    review_pending += 1
                if parameter.status == ValueStatus.ACCEPTED:
                    accepted = True
                confidence_sum += parameter.confidence
                confidence_count += 1
            if accepted:
                covered += 1
        parts_total = len(self._parts)
        tokens_in = sum(call.tokens_in for call in self._llm_calls)
        tokens_out = sum(call.tokens_out for call in self._llm_calls)
        cost = sum(call.cost for call in self._llm_calls)
        return StatsResponse(
            parts_total=parts_total,
            parts_by_family=parts_by_family,
            parts_by_lifecycle=parts_by_lifecycle,
            parts_by_manufacturer=parts_by_manufacturer,
            parameters_total=parameters_total,
            values_by_status=values_by_status,
            values_by_method=values_by_method,
            review_pending=review_pending,
            sources_total=len(self._sources),
            coverage_pct=round(100.0 * covered / parts_total, 2) if parts_total else 0.0,
            mean_confidence=(
                round(confidence_sum / confidence_count, 4) if confidence_count else 0.0
            ),
            llm_calls_total=len(self._llm_calls),
            llm_tokens_in=tokens_in,
            llm_tokens_out=tokens_out,
            llm_cost_total=round(cost, 6),
            avg_cost_per_datasheet=round(cost / parts_total, 6) if parts_total else 0.0,
        )


class FakeLLMExtractor:
    """A fake :class:`~shared.interfaces.LLMExtractor`.

    It never calls a model. Every method counts its calls so a test can prove
    that a path did **not** use the LLM.
    """

    def __init__(
        self,
        filters: dict[str, SearchFilter] | None = None,
        *,
        explanation: str = "Close match with a slightly different footprint.",
        names: dict[str, str] | None = None,
        tier2_result: ExtractionResult | None = None,
        tier3_result: ExtractionResult | None = None,
        raise_on_filter: bool = False,
        raise_on_explain: bool = False,
    ) -> None:
        self.filters = dict(filters or {})
        self.explanation = explanation
        self.names = dict(names or {})
        self.tier2_result = tier2_result
        self.tier3_result = tier3_result
        self.raise_on_filter = raise_on_filter
        self.raise_on_explain = raise_on_explain
        self.queries: list[str] = []
        self.call_counts: dict[str, int] = {
            "build_search_filter": 0,
            "map_name": 0,
            "explain_alternative": 0,
            "extract_tier2": 0,
            "extract_tier3": 0,
        }

    def _count(self, name: str) -> None:
        self.call_counts[name] = self.call_counts.get(name, 0) + 1

    def build_search_filter(self, query: str) -> SearchFilter:
        """Turn a natural-language query into a validated filter."""
        self._count("build_search_filter")
        self.queries.append(query)
        if self.raise_on_filter:
            raise RuntimeError("the model is not available")
        if query in self.filters:
            return self.filters[query].model_copy(deep=True)
        text = (query or "").lower()
        family: Family | None = None
        if "driver" in text:
            family = Family.GATE_DRIVER
        elif "mosfet" in text or "fet" in text:
            family = Family.MOSFET
        return SearchFilter(family=family)

    def map_name(self, raw_name: str, family: Family) -> str | None:
        """Propose a standard parameter name for an unknown raw name."""
        self._count("map_name")
        if self.raise_on_filter:
            raise RuntimeError("the model is not available")
        return self.names.get(raw_name)

    def explain_alternative(self, differences: dict[str, dict[str, float | None]], mpn: str) -> str:
        """Return one short sentence describing the trade-off."""
        self._count("explain_alternative")
        if self.raise_on_explain:
            raise RuntimeError("the model is not available")
        return self.explanation

    def extract_tier2(
        self,
        pages: Any,
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Tier 2: structured output over page text and table data."""
        self._count("extract_tier2")
        if self.tier2_result is not None:
            return self.tier2_result.model_copy(deep=True)
        return ExtractionResult(part_id=part_id, family=family, method=ExtractionMethod.TIER2)

    def extract_tier3(
        self,
        page_images: Any,
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Tier 3: structured output over rendered page images."""
        self._count("extract_tier3")
        if self.tier3_result is not None:
            return self.tier3_result.model_copy(deep=True)
        return ExtractionResult(part_id=part_id, family=family, method=ExtractionMethod.TIER3)


class FakeTier1Extractor:
    """A fake :class:`~shared.interfaces.Tier1Extractor`."""

    def __init__(
        self,
        result: ExtractionResult | None = None,
        *,
        pages: list[int] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.pages = list(pages or [])
        self.error = error
        self.calls: list[tuple[str, Family | None]] = []

    def extract(self, pdf_path: str, family: Family | None = None) -> ExtractionResult:
        """Extract values from the PDF at ``pdf_path``."""
        self.calls.append((pdf_path, family))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result.model_copy(deep=True)
        return ExtractionResult(
            family=family,
            method=ExtractionMethod.TIER1,
            values=[
                ParameterValue(
                    name="vds_max",
                    value=100.0,
                    unit="V",
                    method=ExtractionMethod.TIER1,
                    confidence=0.85,
                )
            ],
        )

    def find_pages(self, pdf_path: str) -> list[int]:
        """Return the 1-based page numbers that hold characteristics tables."""
        return list(self.pages)


class FakeValidator:
    """A fake :class:`~shared.interfaces.Validator`.

    It returns the value with a bumped confidence, so a test can see that the
    validator was used.
    """

    def __init__(self, bump: float = 0.05) -> None:
        self.bump = bump
        self.calls: list[ParameterValue] = []

    def validate(self, value: ParameterValue, api_value: float | None = None) -> ParameterValue:
        """Return a copy of ``value`` with the confidence bumped."""
        self.calls.append(value)
        updated = value.model_copy(deep=True)
        updated.confidence = min(1.0, max(0.0, updated.confidence + self.bump))
        updated.status = ValueStatus.ACCEPTED
        return updated

    def validate_many(
        self,
        values: Any,
        api_values: dict[str, float] | None = None,
    ) -> list[ParameterValue]:
        """Validate a batch of values."""
        return [self.validate(value) for value in values]

    def normalize(self, value: float | None, unit: str | None) -> tuple[float | None, str | None]:
        """Convert ``value`` to the canonical unit."""
        return value, unit
