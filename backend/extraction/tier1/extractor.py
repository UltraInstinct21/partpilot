"""Tier 1: rule based extraction from a datasheet PDF.

The extractor implements the ``Tier1Extractor`` protocol of
``shared.interfaces``:

* ``extract(pdf_path, family=None) -> ExtractionResult``
* ``find_pages(pdf_path) -> list[int]``

Rules that this module never breaks (NFR-03, plan section 5.1):

* a value is only stored when it was read unambiguously from a table cell,
* every value carries ``source_id``, ``page``, ``method``, ``confidence``,
  ``condition`` and the raw text it came from,
* a field that could not be read is reported in ``failed_fields`` - never
  guessed,
* a scanned (image only) PDF yields no values at all; it is handed to tier 3.

Owner: agent b-tier1.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable

from shared.schemas import (
    ExtractionMethod,
    ExtractionResult,
    Family,
    ParameterValue,
    ValueStatus,
)

from .namemap import (
    FAMILY_FIELDS,
    LABEL_ALIASES,
    SYMBOL_ALIASES,
    NameMap,
    NameMatch,
    normalise_label,
    normalise_symbol,
)
from .page_finder import find_pages
from .parsing import clean_cell
from .rows import ParsedRow, detect_schema, parse_row
from .scanned import is_scanned
from .tables import ExtractedTable, extract_tables

__all__ = ["BASE_CONFIDENCE", "PdfTier1Extractor", "Tier1Extractor"]

#: Base confidence of a tier-1 value (the validator adds its own checks).
BASE_CONFIDENCE = 0.85

#: Textual fields: the value is a text, not a number.
_TEXT_FIELDS = frozenset({"package"})

_IO_SYMBOL_RE = re.compile(r"^IO(\d*)[+\-]$")


class PdfTier1Extractor:
    """Rule based tier-1 extractor.

    Parameters
    ----------
    name_map:
        Optional :class:`~extraction.tier1.namemap.NameMap`.  When it carries
        a ``lookup`` callable, that callable is the authority for the name
        mapping (this is how the database agent plugs in the ``name_map``
        table).
    source_id:
        Default provenance id of the PDF (the caller may override it per
        extraction).
    fuzzy_threshold:
        Minimum rapidfuzz score of the fuzzy name fallback (default 90).
    """

    def __init__(
        self,
        name_map: NameMap | None = None,
        *,
        source_id: str | None = None,
        fuzzy_threshold: float = 90.0,
    ) -> None:
        self.name_map = name_map or NameMap(fuzzy_threshold=fuzzy_threshold)
        self.source_id = source_id

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def find_pages(self, pdf_path: str) -> list[int]:
        """Return the 1-based page numbers that hold characteristics tables."""
        return find_pages(pdf_path)

    def extract(
        self,
        pdf_path: str,
        family: Family | None = None,
        *,
        source_id: str | None = None,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Extract the parameter values of a datasheet PDF."""
        started = time.perf_counter()
        resolved_source = source_id if source_id is not None else self.source_id

        if is_scanned(pdf_path):
            return ExtractionResult(
                part_id=part_id,
                family=family,
                method=ExtractionMethod.TIER1,
                source_id=resolved_source,
                values=[],
                pages_used=[],
                failed_fields=list(FAMILY_FIELDS.get(family, ())) if family else [],
                scanned=True,
                notes=(
                    "No text layer: the PDF is a scanned image. Tier 1 cannot read "
                    "any value - hand it to tier 3 (vision)."
                ),
                duration_ms=_elapsed_ms(started),
            )

        pages = self.find_pages(pdf_path)
        tables = extract_tables(pdf_path, pages or None)
        rows = self._collect_rows(tables)

        resolved_family = family or self._infer_family(rows)
        values, notes = self._build_values(rows, resolved_family, resolved_source)

        found = {value.name for value in values}
        expected_fields = FAMILY_FIELDS.get(resolved_family, ()) if resolved_family else ()
        failed = [name for name in expected_fields if name not in found]

        pages_used = sorted({value.page for value in values if value.page is not None})

        return ExtractionResult(
            part_id=part_id,
            family=resolved_family,
            method=ExtractionMethod.TIER1,
            source_id=resolved_source,
            values=values,
            pages_used=pages_used,
            failed_fields=failed,
            scanned=False,
            notes="; ".join(notes) if notes else None,
            duration_ms=_elapsed_ms(started),
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _collect_rows(self, tables: Iterable[ExtractedTable]) -> list[ParsedRow]:
        rows: list[ParsedRow] = []
        for table in tables:
            schema = detect_schema(table.rows)
            start = 0 if schema.header_index is None else schema.header_index + 1
            for raw_row in table.rows[start:]:
                parsed = parse_row(raw_row, schema, table.page)
                if parsed is not None:
                    rows.append(parsed)
        return rows

    def _infer_family(self, rows: list[ParsedRow]) -> Family | None:
        """Guess the component family from the table content."""
        scores = {Family.MOSFET: 0, Family.GATE_DRIVER: 0}
        for row in rows:
            names: list[str] = []
            for key, table in (
                (normalise_symbol(row.symbol), SYMBOL_ALIASES),
                (normalise_label(row.label), LABEL_ALIASES),
            ):
                if not key:
                    continue
                value = table.get(key)
                if value is None:
                    continue
                names.extend(value if isinstance(value, tuple) else (value,))
            for name in names:
                for candidate in (Family.MOSFET, Family.GATE_DRIVER):
                    if name in FAMILY_FIELDS[candidate]:
                        scores[candidate] += 1
        mosfet, gate_driver = scores[Family.MOSFET], scores[Family.GATE_DRIVER]
        if mosfet == 0 and gate_driver == 0:
            return None
        if mosfet == gate_driver:
            return None
        return Family.MOSFET if mosfet > gate_driver else Family.GATE_DRIVER

    def _build_values(
        self,
        rows: list[ParsedRow],
        family: Family | None,
        source_id: str | None,
    ) -> tuple[list[ParameterValue], list[str]]:
        values: list[ParameterValue] = []
        notes: list[str] = []
        seen: set[str] = set()

        for row in rows:
            match = self.name_map.match(row.label, symbol=row.symbol, family=family)
            if match is None:
                continue  # not a parameter we know - skip it silently
            for value in self._values_for_row(row, match, source_id):
                if value.name in seen:
                    continue  # first occurrence wins (document order)
                seen.add(value.name)
                values.append(value)

        if family is Family.GATE_DRIVER and "channel_count" not in seen:
            derived = self._derive_channel_count(rows, source_id)
            if derived is not None:
                values.append(derived)
                seen.add("channel_count")
                notes.append(
                    "channel_count derived from the output current symbols "
                    "(IO+/IO- pair) - not read from a table cell"
                )

        return values, notes

    def _values_for_row(
        self,
        row: ParsedRow,
        match: NameMatch,
        source_id: str | None,
    ) -> list[ParameterValue]:
        names = match.names
        match_confidence = match.confidence
        matched_by = match.matched_by

        if len(names) == 2 and names[0].endswith("_min") and names[1].endswith("_max"):
            return self._compound_values(row, names, match_confidence, source_id)

        name = names[0]
        if name in _TEXT_FIELDS:
            return self._text_value(row, name, match_confidence, source_id)

        parsed = row.values
        if not parsed.has_value:
            return []

        value = parsed.point
        if value is None and parsed.comparator is None:
            return []

        confidence = self._confidence(row, match_confidence, matched_by)

        return [
            ParameterValue(
                name=name,
                value=self._scale(value, row.unit_scale),
                value_min=self._scale(parsed.minimum, row.unit_scale),
                value_typ=self._scale(
                    parsed.typical if row.promote_typical else None, row.unit_scale
                ),
                value_max=self._scale(parsed.maximum, row.unit_scale),
                unit=row.unit,
                condition=dict(row.conditions),
                source_id=source_id,
                page=row.page,
                method=ExtractionMethod.TIER1,
                confidence=confidence,
                status=ValueStatus.REVIEW,
                raw_text=row.raw,
                value_text=row.value_text or None,
            )
        ]

    def _compound_values(
        self,
        row: ParsedRow,
        names: tuple[str, ...],
        match_confidence: float,
        source_id: str | None,
    ) -> list[ParameterValue]:
        """A row that carries a minimum and a maximum (supply, temperature)."""
        parsed = row.values
        if not parsed.has_value:
            return []

        minimum_name, maximum_name = names
        confidence = self._confidence(row, match_confidence, "compound")
        result: list[ParameterValue] = []

        def _make(name: str, value: float | None, low: float | None, high: float | None) -> None:
            result.append(
                ParameterValue(
                    name=name,
                    value=self._scale(value, row.unit_scale),
                    value_min=self._scale(low, row.unit_scale),
                    value_typ=None,
                    value_max=self._scale(high, row.unit_scale),
                    unit=row.unit,
                    condition=dict(row.conditions),
                    source_id=source_id,
                    page=row.page,
                    method=ExtractionMethod.TIER1,
                    confidence=confidence,
                    status=ValueStatus.REVIEW,
                    raw_text=row.raw,
                    value_text=row.value_text or None,
                )
            )

        if parsed.minimum is not None:
            _make(minimum_name, parsed.minimum, parsed.minimum, None)
        if parsed.maximum is not None:
            _make(maximum_name, parsed.maximum, None, parsed.maximum)
        if parsed.minimum is None and parsed.maximum is None:
            # a single rating: it is the upper limit
            point = parsed.point
            if point is not None:
                _make(maximum_name, point, None, None)
        return result

    def _text_value(
        self,
        row: ParsedRow,
        name: str,
        match_confidence: float,
        source_id: str | None,
    ) -> list[ParameterValue]:
        text = clean_cell(row.value_text)
        if not text:
            return []
        return [
            ParameterValue(
                name=name,
                value=None,
                value_min=None,
                value_typ=None,
                value_max=None,
                unit=None,
                condition=dict(row.conditions),
                source_id=source_id,
                page=row.page,
                method=ExtractionMethod.TIER1,
                confidence=min(0.85, match_confidence),
                status=ValueStatus.REVIEW,
                raw_text=row.raw,
                value_text=text,
            )
        ]

    def _confidence(self, row: ParsedRow, match_confidence: float, matched_by: str) -> float:
        confidence = min(match_confidence, BASE_CONFIDENCE)
        if matched_by == "fuzzy":
            confidence -= 0.15
        if row.values.is_bound:
            confidence -= 0.10
        if row.unit is None:
            confidence -= 0.10
        if not row.conditions:
            confidence -= 0.05
        return max(0.0, min(1.0, round(confidence, 3)))

    @staticmethod
    def _scale(value: float | None, scale: float) -> float | None:
        if value is None:
            return None
        return value * scale

    def _derive_channel_count(
        self,
        rows: list[ParsedRow],
        source_id: str | None,
    ) -> ParameterValue | None:
        """Derive the number of output channels from the IO symbols.

        A gate driver row ``Peak Source Current (IO+)`` together with
        ``Peak Sink Current (IO-)`` describes one output channel.  The value
        is a structural inference, not a cell that was read, so it carries a
        low confidence.
        """
        groups: set[str] = set()
        page: int | None = None
        for row in rows:
            symbol = normalise_symbol(row.symbol)
            match = _IO_SYMBOL_RE.match(symbol)
            if not match:
                continue
            groups.add(match.group(1) or "0")
            if page is None:
                page = row.page
        if not groups:
            return None
        count = len(groups)
        return ParameterValue(
            name="channel_count",
            value=float(count),
            value_min=None,
            value_typ=None,
            value_max=None,
            unit=None,
            condition={},
            source_id=source_id,
            page=page,
            method=ExtractionMethod.TIER1,
            confidence=0.5,
            status=ValueStatus.REVIEW,
            raw_text=None,
            value_text=str(count),
        )


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))


#: Alias so that ``from extraction.tier1 import Tier1Extractor`` works.
Tier1Extractor = PdfTier1Extractor
