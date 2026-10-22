"""BOM health check (plan WP6, FR-14).

The service reads a BOM CSV, matches every line to a part by MPN and returns a
risk table. It is defensive by design: a broken CSV (no header, wrong number of
columns, empty file, broken quoting) must never raise - the API answers with a
partial result instead.
"""

from __future__ import annotations

import csv
import io
import re
import time
from typing import Final

from shared.interfaces import PartsRepository
from shared.schemas import (
    BomCheckResponse,
    BomLine,
    BomRisk,
    LifecycleStatus,
    PartRecord,
    RiskSeverity,
    SearchFilter,
)

__all__ = ["BomService", "RISK_CODES"]

#: Risk codes raised by the BOM check.
RISK_CODES: Final[tuple[str, ...]] = (
    "obsolete",
    "nrnd",
    "low_stock",
    "single_source",
    "not_found",
    "manufacturer_mismatch",
    "unknown_lifecycle",
)

_MPN_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "mpn",
        "mpn/part number",
        "part number",
        "partnumber",
        "part no",
        "part no.",
        "part_number",
        "pn",
        "pn/part number",
        "manufacturer part number",
        "manufacturer part no",
        "mfr part number",
        "mfr part no",
        "mfr. part number",
        "mfr. part no.",
        "manufacturer part #",
    }
)

_QTY_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "qty",
        "qty.",
        "quantity",
        "quantity ordered",
        "quantity (ordered)",
        "qty ordered",
        "qty req'd",
        "qty reqd",
        "ordered qty",
        "quantity required",
    }
)

_MANUFACTURER_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "manufacturer",
        "mfr",
        "mfr.",
        "mfr name",
        "mfr. name",
        "manufacturer name",
        "mfg",
        "brand",
    }
)

_REFERENCE_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "reference",
        "references",
        "ref",
        "ref.",
        "ref des",
        "refdes",
        "designator",
        "designators",
    }
)

_ANY_HEADER: Final[frozenset[str]] = (
    _MPN_HEADERS | _QTY_HEADERS | _MANUFACTURER_HEADERS | _REFERENCE_HEADERS
)

_SEVERITY_ORDER: Final[dict[RiskSeverity, int]] = {
    RiskSeverity.INFO: 0,
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}

_NORMALISE_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def _normalise_header(cell: str) -> str:
    """Normalise a header cell so that ``"MPN"`` and ``"mfr part no."`` match."""
    text = (cell or "").strip().lower()
    text = text.replace("*", " ")
    return " ".join(text.split())


def _normalise_company(name: str) -> str:
    """Normalise a manufacturer name for a containment comparison."""
    return _NORMALISE_RE.sub("", (name or "").lower())


def _manufacturers_agree(left: str, right: str) -> bool:
    """Return ``True`` when two manufacturer names do not contradict."""
    a = _normalise_company(left)
    b = _normalise_company(right)
    if not a or not b:
        return True
    if a == b:
        return True
    return a in b or b in a


class BomService:
    """Check a BOM CSV and report the risks (FR-14).

    Args:
        repository: the injected :class:`~shared.interfaces.PartsRepository`.
        low_stock_threshold: total stock below this value is a ``low_stock``
            risk.
        single_source_max: a part offered by at most this many distributors
            is a ``single_source`` risk.
    """

    def __init__(
        self,
        repository: PartsRepository,
        *,
        low_stock_threshold: int = 1000,
        single_source_max: int = 1,
    ) -> None:
        self._repository = repository
        self._low_stock_threshold = int(low_stock_threshold)
        self._single_source_max = int(single_source_max)

    # -- parsing ----------------------------------------------------------------

    @staticmethod
    def _detect_delimiter(sample: str) -> str:
        """Return the delimiter of the CSV (``","``, ``";"`` or a tab)."""
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            if dialect.delimiter:
                return dialect.delimiter
        except (csv.Error, TypeError):
            pass
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {
            ",": first_line.count(","),
            ";": first_line.count(";"),
            "\t": first_line.count("\t"),
        }
        best = max(counts, key=lambda key: counts[key])
        return best if counts[best] > 0 else ","

    @staticmethod
    def _parse_rows(content: str, delimiter: str = ",") -> list[list[str]]:
        """Parse the CSV into rows. Never raises."""
        text = content.replace("\r\n", "\n").replace("\r", "\n")
        if text.startswith("\ufeff"):
            text = text[1:]
        rows: list[list[str]] = []
        try:
            for row in csv.reader(io.StringIO(text), delimiter=delimiter, skipinitialspace=True):
                rows.append([str(cell).strip() for cell in row])
        except csv.Error:
            # Fall back to a plain split so that a broken file still yields
            # something usable.
            for line in text.splitlines():
                rows.append([cell.strip() for cell in line.split(delimiter)])
        return rows

    @staticmethod
    def _detect_columns(header: list[str]) -> dict[str, int]:
        """Return the column indexes of the known header names."""
        columns: dict[str, int] = {}
        for index, cell in enumerate(header):
            name = _normalise_header(cell)
            if name in _MPN_HEADERS and "mpn" not in columns:
                columns["mpn"] = index
            elif name in _QTY_HEADERS and "qty" not in columns:
                columns["qty"] = index
            elif name in _MANUFACTURER_HEADERS and "manufacturer" not in columns:
                columns["manufacturer"] = index
            elif name in _REFERENCE_HEADERS and "reference" not in columns:
                columns["reference"] = index
        return columns

    @staticmethod
    def _is_header(row: list[str]) -> bool:
        return any(_normalise_header(cell) in _ANY_HEADER for cell in row)

    @staticmethod
    def _to_quantity(cell: str) -> int:
        try:
            value = float((cell or "").replace(",", "."))
        except (TypeError, ValueError):
            return 1
        if value <= 0:
            return 1
        return int(value)

    # -- matching ---------------------------------------------------------------

    def _find_part(self, mpn: str) -> PartRecord | None:
        """Match one MPN against the repository."""
        if not mpn:
            return None
        part = self._repository.get_part_by_mpn(mpn)
        if part is not None:
            return part
        try:
            summaries, _total = self._repository.list_parts(
                SearchFilter(mpn_contains=mpn), limit=25, offset=0
            )
        except Exception:  # pragma: no cover - defensive
            return None
        exact = [
            item for item in summaries if (item.mpn or "").strip().lower() == mpn.strip().lower()
        ]
        if exact:
            found = self._repository.get_part(exact[0].part_id)
            if found is not None:
                return found
        if summaries:
            return self._repository.get_part(summaries[0].part_id)
        return None

    # -- risks ------------------------------------------------------------------

    def _risks_for(self, part: PartRecord, line_manufacturer: str | None) -> list[BomRisk]:
        risks: list[BomRisk] = []
        lifecycle = part.lifecycle_status
        if lifecycle == LifecycleStatus.OBSOLETE:
            risks.append(
                BomRisk(
                    code="obsolete",
                    severity=RiskSeverity.CRITICAL,
                    message=f"{part.mpn} is obsolete",
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Choose a drop-in replacement or redesign the circuit.",
                )
            )
        elif lifecycle == LifecycleStatus.NRND:
            risks.append(
                BomRisk(
                    code="nrnd",
                    severity=RiskSeverity.MEDIUM,
                    message=f"{part.mpn} is not recommended for new designs",
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Plan a migration to an active part.",
                )
            )
        elif lifecycle == LifecycleStatus.UNKNOWN:
            risks.append(
                BomRisk(
                    code="unknown_lifecycle",
                    severity=RiskSeverity.LOW,
                    message=f"The lifecycle status of {part.mpn} is unknown",
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Ask the manufacturer for the lifecycle status.",
                )
            )

        distributors: set[str] = set()
        total_stock = 0
        for offer in part.offers:
            if offer.distributor:
                distributors.add(offer.distributor.strip().lower())
            total_stock += int(offer.stock or 0)
        if part.offers and total_stock < self._low_stock_threshold:
            risks.append(
                BomRisk(
                    code="low_stock",
                    severity=RiskSeverity.MEDIUM,
                    message=(
                        f"{part.mpn} has only {total_stock} pieces in stock "
                        f"(threshold {self._low_stock_threshold})"
                    ),
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Order early or pick a part with more stock.",
                )
            )
        if distributors and len(distributors) <= self._single_source_max:
            risks.append(
                BomRisk(
                    code="single_source",
                    severity=RiskSeverity.LOW,
                    message=f"{part.mpn} is only offered by one distributor",
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Qualify a second source.",
                )
            )

        if line_manufacturer and not _manufacturers_agree(line_manufacturer, part.manufacturer):
            risks.append(
                BomRisk(
                    code="manufacturer_mismatch",
                    severity=RiskSeverity.MEDIUM,
                    message=(
                        f"The BOM says '{line_manufacturer}' but {part.mpn} is made by "
                        f"'{part.manufacturer}'"
                    ),
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Check the part number and the manufacturer.",
                )
            )
        return risks

    # -- protocol ---------------------------------------------------------------

    def check_csv(self, content: str, filename: str | None = None) -> BomCheckResponse:
        """Parse the BOM CSV and return the risk table."""
        started = time.perf_counter()
        text = content or ""
        if not text.strip():
            return BomCheckResponse(
                filename=filename,
                total_lines=0,
                matched_lines=0,
                unmatched_lines=0,
                risk_count=0,
                highest_severity=None,
                lines=[],
                risks=[],
                took_ms=int((time.perf_counter() - started) * 1000),
            )

        delimiter = self._detect_delimiter(text[:4096])
        rows = self._parse_rows(text, delimiter)
        rows = [row for row in rows if any(cell for cell in row)]
        if not rows:
            return BomCheckResponse(filename=filename, took_ms=0)

        has_header = self._is_header(rows[0])
        columns: dict[str, int] = {}
        data_rows = rows
        if has_header:
            columns = self._detect_columns(rows[0])
            data_rows = rows[1:]
        mpn_index = columns.get("mpn", 0)
        qty_index = columns.get("qty")
        manufacturer_index = columns.get("manufacturer")
        reference_index = columns.get("reference")

        lines: list[BomLine] = []
        all_risks: list[BomRisk] = []
        matched_lines = 0
        highest: RiskSeverity | None = None

        for offset, row in enumerate(data_rows):
            line_number = offset + (2 if has_header else 1)
            mpn = row[mpn_index].strip() if mpn_index < len(row) else ""
            quantity = (
                self._to_quantity(row[qty_index])
                if qty_index is not None and qty_index < len(row)
                else 1
            )
            manufacturer = (
                row[manufacturer_index].strip()
                if manufacturer_index is not None and manufacturer_index < len(row)
                else None
            )
            reference = (
                row[reference_index].strip()
                if reference_index is not None and reference_index < len(row)
                else None
            )

            risks: list[BomRisk] = []
            part = self._find_part(mpn) if mpn else None
            if part is None:
                risks.append(
                    BomRisk(
                        code="not_found",
                        severity=RiskSeverity.HIGH,
                        message=(
                            f"No part matches '{mpn}'" if mpn else "The line has no part number"
                        ),
                        mpn=mpn or None,
                        suggestion="Check the part number and the manufacturer.",
                    )
                )
            else:
                matched_lines += 1
                risks.extend(self._risks_for(part, manufacturer))

            for risk in risks:
                if highest is None or _SEVERITY_ORDER[risk.severity] > _SEVERITY_ORDER[highest]:
                    highest = risk.severity
            all_risks.extend(risks)

            lines.append(
                BomLine(
                    line_number=line_number,
                    mpn=mpn,
                    quantity=quantity,
                    manufacturer=manufacturer or None,
                    reference=reference or None,
                    matched_part_id=part.part_id if part is not None else None,
                    matched=part is not None,
                    risks=risks,
                )
            )

        return BomCheckResponse(
            filename=filename,
            total_lines=len(lines),
            matched_lines=matched_lines,
            unmatched_lines=len(lines) - matched_lines,
            risk_count=len(all_risks),
            highest_severity=highest,
            lines=lines,
            risks=all_risks,
            took_ms=int((time.perf_counter() - started) * 1000),
        )
