"""In-memory parts repository backed by the recorded seed fixture.

The repository implements the ``PartsRepository`` protocol of
``shared.interfaces`` completely - including a *real* filter implementation -
so the API can be developed and tested before the database agent lands.

Data source: ``contracts/fixtures/seed/parts.json`` (30 synthetic parts).
No network access, no LLM, no real distributor data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.config import Settings, get_settings
from shared.schemas import (
    ExtractionMethod,
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
    SourceType,
    StatsResponse,
    ValueStatus,
)

# Parameters that live on page 1 (absolute maximum ratings) of a datasheet.
PAGE_ONE_FIELDS = frozenset(
    {
        "vds_max",
        "id_continuous",
        "max_junction_temp",
        "supply_voltage_min",
        "supply_voltage_max",
        "peak_source_current",
        "peak_sink_current",
        "channel_count",
    }
)

# Parameters that the fake marks as "needs a human" so the review queue is not empty.
REVIEW_FIELDS: dict[str, frozenset[str]] = {
    "mosfet": frozenset({"vgs_threshold", "reverse_recovery_qrr"}),
    "gate_driver": frozenset({"propagation_delay", "input_logic_level"}),
}

# The parameters that are shown in a summary card.
KEY_PARAMETER_ORDER = (
    "vds_max",
    "rds_on",
    "id_continuous",
    "total_gate_charge_qg",
    "supply_voltage_max",
    "peak_source_current",
)

_FAMILY_PDF = {
    "mosfet": "synthetic_mosfet.pdf",
    "gate_driver": "synthetic_gate_driver.pdf",
}


def _digest_int(text: str) -> int:
    """A stable pseudo random integer for a string (no ``hash()``: it is salted)."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


class InMemoryPartsRepository:
    """A working repository that keeps everything in memory.

    Args:
        settings: Runtime settings; the seed fixture is read from
            ``settings.fixtures_dir / "seed" / "parts.json"``.
        seed_path: Override for the seed fixture path.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        seed_path: Path | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._seed_path = seed_path or (self._settings.fixtures_dir / "seed" / "parts.json")
        self._parts: dict[str, PartRecord] = {}
        self._parameters: dict[str, ParameterValue] = {}
        self._sources: dict[str, SourceRef] = {}
        self._offers: dict[str, list[Offer]] = {}
        self._llm_calls: list[LLMCallRecord] = []
        self._load_seed()

    # ------------------------------------------------------------------ seed

    def _load_seed(self) -> None:
        """Load the seed fixture into memory."""
        if not self._seed_path.exists():
            return
        payload = json.loads(self._seed_path.read_text(encoding="utf-8"))
        for raw in payload.get("parts", []):
            self._add_seed_part(raw)

    def _add_seed_part(self, raw: dict[str, Any]) -> None:
        family = Family(raw["family"])
        part = PartRecord(
            part_id=raw["part_id"],
            mpn=raw["mpn"],
            manufacturer=raw["manufacturer"],
            family=family,
            package=raw.get("package"),
            lifecycle_status=LifecycleStatus(raw.get("lifecycle_status", "unknown")),
            datasheet_url=raw.get("datasheet_url"),
            description=raw.get("description"),
            updated_at=datetime.now(UTC),
        )

        # API sources that the fixture mentions.
        for source_id in raw.get("source_ids", []):
            distributor = source_id.split("-")[1] if "-" in source_id else None
            self.add_source(
                SourceRef(
                    source_id=source_id,
                    url=f"https://example.invalid/api/{distributor or 'catalogue'}/{part.mpn}",
                    type=SourceType.API,
                    distributor=distributor,
                    note="seed fixture",
                )
            )

        # A datasheet source that points at the synthetic PDF of the family.
        pdf_source = self._make_pdf_source(part)
        part.source_ids = [*raw.get("source_ids", []), pdf_source.source_id]

        review_fields = REVIEW_FIELDS.get(family.value, frozenset())
        for name, spec in (raw.get("parameters") or {}).items():
            value = spec.get("value")
            unit = spec.get("unit")
            needs_review = name in review_fields
            parameter = ParameterValue(
                param_id=f"{part.part_id}::{name}",
                part_id=part.part_id,
                name=name,
                value=value,
                unit=unit,
                condition=spec.get("condition") or {},
                source_id=pdf_source.source_id,
                page=1 if name in PAGE_ONE_FIELDS else 2,
                method=ExtractionMethod.TIER2 if needs_review else ExtractionMethod.TIER1,
                confidence=0.62 if needs_review else 0.9,
                status=ValueStatus.REVIEW if needs_review else ValueStatus.ACCEPTED,
                value_text=None if value is None else f"{value} {unit or ''}".strip(),
            )
            self._parameters[parameter.param_id or ""] = parameter
            part.parameters.append(parameter)

        self._parts[part.part_id] = part
        self._seed_offers(part, raw)

    def _make_pdf_source(self, part: PartRecord) -> SourceRef:
        """Create the datasheet source of a part (the synthetic fixture PDF)."""
        pdf_name = _FAMILY_PDF.get(part.family.value)
        pdf_path = self._settings.fixtures_dir / "pdfs" / pdf_name if pdf_name else None
        source = SourceRef(
            source_id=f"pdf-{part.part_id}",
            url=part.datasheet_url or f"https://example.invalid/datasheets/{part.mpn}.pdf",
            type=SourceType.PDF,
            distributor=None,
            local_path=str(pdf_path) if pdf_path and pdf_path.exists() else None,
            page_count=2 if pdf_path and pdf_path.exists() else None,
            content_type="application/pdf",
            note="synthetic seed datasheet",
        )
        self.add_source(source)
        return source

    def _seed_offers(self, part: PartRecord, raw: dict[str, Any] | None = None) -> None:
        """Create the distributor offers of a part.

        The seed fixture carries the offers (with the stock numbers that make
        the BOM risks reachable), so they are used when they are there. The
        deterministic fallback keeps the fake usable with an older fixture.
        """
        raw_offers = (raw or {}).get("offers") or []
        if raw_offers:
            for entry in raw_offers:
                offer = Offer(
                    part_id=part.part_id,
                    distributor=str(entry.get("distributor") or "unknown"),
                    sku=entry.get("sku"),
                    stock=entry.get("stock"),
                    unit_price=entry.get("unit_price"),
                    currency=entry.get("currency") or "USD",
                    lead_time_days=1 + _digest_int(part.part_id) % 21,
                    fetched_at=datetime.now(UTC),
                    url=entry.get("url"),
                    price_breaks=[
                        {"quantity": 1, "unit_price": entry.get("unit_price")},
                    ],
                )
                self._offers.setdefault(part.part_id, []).append(offer)
                part.offers.append(offer)
            return

        for distributor, sku in (("digikey", f"DK-{part.mpn}"), ("mouser", f"MO-{part.mpn}")):
            seed = _digest_int(f"{distributor}:{part.part_id}")
            stock = 0 if seed % 7 == 0 else 100 + seed % 9000
            offer = Offer(
                part_id=part.part_id,
                distributor=distributor,
                sku=sku,
                stock=stock,
                unit_price=round(0.35 + (seed % 900) / 100, 2),
                currency="USD",
                lead_time_days=1 + seed % 21,
                fetched_at=datetime.now(UTC),
                url=f"https://example.invalid/{distributor}/{part.mpn}",
                price_breaks=[{"quantity": 1, "unit_price": round(0.35 + (seed % 900) / 100, 2)}],
            )
            self._offers.setdefault(part.part_id, []).append(offer)
            part.offers.append(offer)

    # ----------------------------------------------------------------- parts

    def add_part(self, part: PartRecord) -> PartRecord:
        """Insert or update a part and its values."""
        self._parts[part.part_id] = part
        for parameter in part.parameters:
            if parameter.param_id:
                self._parameters[parameter.param_id] = parameter
        return part

    def get_part(self, part_id: str) -> PartRecord | None:
        """Return one part with all values and offers."""
        part = self._parts.get(part_id)
        if part is None:
            return None
        clone = part.model_copy(deep=True)
        clone.offers = list(self._offers.get(part_id, []))
        clone.parameters = [
            self._parameters[p.param_id or ""] for p in part.parameters if p.param_id
        ]
        return clone

    def get_part_by_mpn(self, mpn: str) -> PartRecord | None:
        """Return one part looked up by manufacturer part number."""
        needle = (mpn or "").strip().lower()
        if not needle:
            return None
        for part in self._parts.values():
            if part.mpn.lower() == needle:
                return self.get_part(part.part_id)
        return None

    def list_parts(
        self,
        filt: SearchFilter | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PartSummary], int]:
        """Return a page of parts matching ``filt`` and the total match count."""
        parts = list(self._parts.values())
        if filt is not None:
            parts = [part for part in parts if self._matches(part, filt)]
        parts.sort(key=lambda part: (part.manufacturer.lower(), part.mpn.lower()))
        total = len(parts)
        window = parts[offset : offset + limit] if limit else []
        return [self._to_summary(part) for part in window], total

    def get_parameters(self, part_id: str) -> list[ParameterValue]:
        """Return every stored value of a part."""
        part = self._parts.get(part_id)
        if part is None:
            return []
        return [self._parameters[p.param_id or ""] for p in part.parameters if p.param_id]

    def get_parameter(self, param_id: str) -> ParameterValue | None:
        """Return one value by id."""
        return self._parameters.get(param_id)

    def update_parameter(self, value: ParameterValue) -> ParameterValue:
        """Persist a changed value."""
        param_id = value.param_id or ""
        self._parameters[param_id] = value
        part = self._parts.get(value.part_id or "")
        if part is not None:
            for index, existing in enumerate(part.parameters):
                if existing.param_id == param_id:
                    part.parameters[index] = value
                    break
        return value

    # --------------------------------------------------------------- sources

    def add_source(self, source: SourceRef) -> SourceRef:
        """Insert or update a source record."""
        self._sources[source.source_id] = source
        return source

    def get_source(self, source_id: str) -> SourceRef | None:
        """Return one source by id."""
        return self._sources.get(source_id)

    def get_source_page(self, source_id: str, page: int) -> SourcePage | None:
        """Return one page of a source (text and image reference)."""
        source = self._sources.get(source_id)
        if source is None or page < 1:
            return None
        local_path = source.local_path
        if not local_path:
            return None
        path = Path(local_path)
        if not path.exists():
            return None
        try:
            import pymupdf

            with pymupdf.open(path) as document:
                if page > document.page_count:
                    return None
                pdf_page = document[page - 1]
                rect = pdf_page.rect
                text = pdf_page.get_text()
                width, height = int(rect.width), int(rect.height)
        except Exception:  # pragma: no cover - a broken PDF must not kill the API
            return None
        return SourcePage(
            source_id=source_id,
            page=page,
            width=width,
            height=height,
            text=text,
            image_url=f"/api/sources/{source_id}/page/{page}?format=image",
            is_image_only=not text.strip(),
        )

    def add_offer(self, part_id: str, offer: dict[str, Any]) -> None:
        """Store one distributor offer for a part."""
        model = offer if isinstance(offer, Offer) else Offer(**offer)
        model.part_id = part_id
        self._offers.setdefault(part_id, []).append(model)
        part = self._parts.get(part_id)
        if part is not None:
            part.offers.append(model)

    # --------------------------------------------------------------- review

    def list_review_queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the low-confidence values waiting for review (FR-10)."""
        pending = [
            self._to_review_item(value)
            for value in self._parameters.values()
            if value.status == ValueStatus.REVIEW
        ]
        pending.sort(key=lambda item: item.param_id)
        if offset:
            pending = pending[offset:]
        return pending[:limit] if limit else pending

    def apply_review(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Accept, correct or reject a reviewed value."""
        value = self._parameters.get(param_id)
        if value is None:
            raise KeyError(param_id)
        if decision.action == "accept":
            value.status = ValueStatus.ACCEPTED
            value.confidence = 1.0
            value.method = ExtractionMethod.MANUAL
            message = "Value accepted."
        elif decision.action == "correct":
            value.value = decision.value
            value.value_min = decision.value_min
            value.value_typ = decision.value_typ
            value.value_max = decision.value_max
            if decision.unit is not None:
                value.unit = decision.unit
            if decision.condition:
                value.condition = decision.condition
            value.status = ValueStatus.ACCEPTED
            value.confidence = 1.0
            value.method = ExtractionMethod.MANUAL
            message = "Value corrected."
        else:
            value.status = ValueStatus.REJECTED
            value.confidence = 0.0
            value.method = ExtractionMethod.MANUAL
            message = "Value rejected."
        self.update_parameter(value)
        return ReviewResponse(
            param_id=param_id,
            status=value.status,
            message=message,
            item=self._to_review_item(value),
        )

    # ----------------------------------------------------------------- llm

    def record_llm_call(self, record: LLMCallRecord) -> None:
        """Store one LLM call for cost accounting."""
        self._llm_calls.append(record)

    @property
    def llm_calls(self) -> list[LLMCallRecord]:
        """Every recorded LLM call (newest last)."""
        return list(self._llm_calls)

    # --------------------------------------------------------------- stats

    def stats(self) -> StatsResponse:
        """Return dashboard counts and quality numbers."""
        parts = list(self._parts.values())
        values = list(self._parameters.values())

        parts_by_family: dict[str, int] = {}
        parts_by_lifecycle: dict[str, int] = {}
        parts_by_manufacturer: dict[str, int] = {}
        values_by_status: dict[str, int] = {}
        values_by_method: dict[str, int] = {}

        for part in parts:
            parts_by_family[part.family.value] = parts_by_family.get(part.family.value, 0) + 1
            key = part.lifecycle_status.value
            parts_by_lifecycle[key] = parts_by_lifecycle.get(key, 0) + 1
            parts_by_manufacturer[part.manufacturer] = (
                parts_by_manufacturer.get(part.manufacturer, 0) + 1
            )

        for value in values:
            key = value.status.value
            values_by_status[key] = values_by_status.get(key, 0) + 1
            method = value.method.value if value.method else "unknown"
            values_by_method[method] = values_by_method.get(method, 0) + 1

        confidences = [value.confidence for value in values]
        accepted = values_by_status.get(ValueStatus.ACCEPTED.value, 0)
        cost = sum(record.cost for record in self._llm_calls)
        tokens_in = sum(record.tokens_in for record in self._llm_calls)
        tokens_out = sum(record.tokens_out for record in self._llm_calls)

        return StatsResponse(
            parts_total=len(parts),
            parts_by_family=parts_by_family,
            parts_by_lifecycle=parts_by_lifecycle,
            parts_by_manufacturer=parts_by_manufacturer,
            parameters_total=len(values),
            values_by_status=values_by_status,
            values_by_method=values_by_method,
            review_pending=values_by_status.get(ValueStatus.REVIEW.value, 0),
            sources_total=len(self._sources),
            coverage_pct=round(100.0 * len(values) / max(1, len(parts)), 2),
            mean_confidence=round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            llm_calls_total=len(self._llm_calls),
            llm_tokens_in=tokens_in,
            llm_tokens_out=tokens_out,
            llm_cost_total=round(cost, 6),
            avg_cost_per_datasheet=round(cost / len(parts), 6) if parts else 0.0,
            accuracy={"accepted_pct": round(100.0 * accepted / len(values), 2)} if values else {},
            generated_at=datetime.now(UTC),
        )

    # ------------------------------------------------------------- helpers

    def _to_summary(self, part: PartRecord) -> PartSummary:
        """Build the compact representation of a part."""
        offers = self._offers.get(part.part_id, [])
        stocks = [offer.stock for offer in offers if offer.stock is not None]
        key_parameters: dict[str, float | None] = {}
        for name in KEY_PARAMETER_ORDER:
            for value in part.parameters:
                if value.name == name:
                    key_parameters[name] = value.representative()
                    break
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
            offers_count=len(offers),
            total_stock=sum(stocks) if stocks else None,
        )

    def _to_review_item(self, value: ParameterValue) -> ReviewItem:
        """Build the review queue entry of a value."""
        part = self._parts.get(value.part_id or "")
        reasons = ["confidence below the acceptance threshold"]
        if value.method == ExtractionMethod.TIER2:
            reasons.append("read by the LLM tier")
        return ReviewItem(
            param_id=value.param_id or "",
            part_id=value.part_id or "",
            mpn=part.mpn if part else "",
            manufacturer=part.manufacturer if part else "",
            family=part.family if part else Family.MOSFET,
            name=value.name,
            value=value.value,
            value_min=value.value_min,
            value_typ=value.value_typ,
            value_max=value.value_max,
            unit=value.unit,
            condition=value.condition,
            source_id=value.source_id,
            page=value.page,
            method=value.method,
            confidence=value.confidence,
            status=value.status,
            reasons=reasons,
            raw_text=value.raw_text,
            created_at=datetime.now(UTC),
        )

    # ---------------------------------------------------------- filter logic

    def _matches(self, part: PartRecord, filt: SearchFilter) -> bool:
        """Return ``True`` when a part satisfies the filter."""
        if filt.family is not None and part.family != filt.family:
            return False
        if filt.manufacturer and part.manufacturer.lower() != filt.manufacturer.lower():
            return False
        if filt.manufacturer_in and part.manufacturer.lower() not in {
            item.lower() for item in filt.manufacturer_in
        }:
            return False
        if filt.package and (part.package or "").lower() != filt.package.lower():
            return False
        if filt.package_in and (part.package or "").lower() not in {
            item.lower() for item in filt.package_in
        }:
            return False
        if filt.lifecycle_status and part.lifecycle_status not in filt.lifecycle_status:
            return False
        if filt.mpn_contains and filt.mpn_contains.lower() not in part.mpn.lower():
            return False
        if filt.in_stock is not None:
            total = self._total_stock(part.part_id)
            if filt.in_stock and not total:
                return False
            if not filt.in_stock and total:
                return False
        if filt.text:
            needle = filt.text.lower()
            haystack = " ".join(
                filter(None, [part.mpn, part.manufacturer, part.description, part.package])
            ).lower()
            if needle not in haystack:
                return False
        for constraint in filt.parameters:
            if not self._matches_constraint(part, constraint):
                return False
        return True

    def _total_stock(self, part_id: str) -> int:
        """The summed stock of all offers of a part."""
        return sum(offer.stock or 0 for offer in self._offers.get(part_id, []))

    def _matches_constraint(self, part: PartRecord, constraint: ParameterConstraint) -> bool:
        """Check one numeric constraint against the values of a part."""
        values = [value for value in part.parameters if value.name == constraint.name]
        if not values:
            return False
        for value in values:
            number = value.representative()
            if number is None:
                continue
            converted = convert_unit(number, value.unit, constraint.unit)
            if converted is None:
                continue
            if compare_with_constraint(converted, constraint):
                return True
        return False


# ---------------------------------------------------------------- units


_URG = None


def _get_ureg():  # type: ignore[no-untyped-def]
    """Return a lazily created pint registry (importing pint is slow)."""
    global _URG
    if _URG is None:
        import pint

        _URG = pint.UnitRegistry()
    return _URG


def convert_unit(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Convert ``value`` from one unit to another; ``None`` when impossible."""
    if from_unit is None or to_unit is None or from_unit == to_unit:
        return value
    try:
        ureg = _get_ureg()
        return float(ureg.Quantity(value, from_unit).to(to_unit).magnitude)
    except Exception:
        return None


def compare_with_constraint(number: float, constraint: ParameterConstraint) -> bool:
    """Compare a number with the bound implied by a constraint."""
    operator = constraint.operator
    if operator == "lt":
        target = constraint.max if constraint.max is not None else constraint.typ
        return target is not None and number < target
    if operator == "lte":
        target = constraint.max if constraint.max is not None else constraint.typ
        return target is not None and number <= target
    if operator == "gt":
        target = constraint.min if constraint.min is not None else constraint.typ
        return target is not None and number > target
    if operator == "gte":
        target = constraint.min if constraint.min is not None else constraint.typ
        return target is not None and number >= target
    if operator == "eq":
        target = constraint.typ if constraint.typ is not None else constraint.min
        if target is None:
            target = constraint.max
        return target is not None and abs(number - target) < 1e-9
    lower, upper = constraint.bounds()
    if lower is not None and number < lower:
        return False
    if upper is not None and number > upper:
        return False
    return lower is not None or upper is not None


def iter_all_values(repository: InMemoryPartsRepository) -> Iterable[ParameterValue]:
    """Iterate over every stored value of a repository (helper for tests)."""
    return iter(repository._parameters.values())  # noqa: SLF001 - test helper


__all__ = [
    "InMemoryPartsRepository",
    "compare_with_constraint",
    "convert_unit",
    "iter_all_values",
]
