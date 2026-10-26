"""BOM health check (plan WP6, FR-14).

The service reads a BOM CSV, matches every line to a part by MPN and returns a
risk table. It is defensive by design: a broken CSV (no header, wrong number of
columns, empty file, broken quoting) must never raise - the API answers with a
partial result instead.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final

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
    "footprint_mismatch",
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
        "part-number",
        "part #",
        "part#",
        "pn",
        "p/n",
        "p.n.",
        "pn/part number",
        "manufacturer part number",
        "manufacturer part no",
        "manufacturer part no.",
        "mfr part number",
        "mfr part no",
        "mfr. part number",
        "mfr. part no.",
        "mfr part #",
        "mfr part",
        "mfr pn",
        "mfg part number",
        "mfg part no",
        "mfg part #",
        "component",
        "component name",
        "component part number",
        "device",
        "item",
        "item number",
        "item part number",
        "part",
        "part name",
        "part id",
        "part-id",
        "catalog no",
        "catalog number",
        "catalog #",
        "article",
        "article number",
        "order code",
        "ordering code",
        "digikey part number",
        "digi-key part number",
        "mouser part number",
        "element14 part number",
        "lcsc part #",
        "lcsc part number",
        "designation",
        "value",
        "val",
        "comment",
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
        "count",
        "amount",
        "total qty",
        "total quantity",
        "pcs",
        "pieces",
        "units",
        "number",
        "no of items",
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
        "mfg.",
        "brand",
        "vendor",
        "producer",
        "maker",
        "company",
    }
)

_REFERENCE_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "reference",
        "references",
        "ref",
        "ref.",
        "ref des",
        "ref. des",
        "refdes",
        "ref_des",
        "designator",
        "designators",
        "loc",
        "location",
        "locations",
        "placement",
    }
)

_VALUE_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "value",
        "values",
        "val",
        "device",
        "component",
        "component value",
        "item value",
        "comment",
        "designation",
    }
)

_FOOTPRINT_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "footprint",
        "footprints",
        "package",
        "pkg",
        "case",
        "housing",
        "pattern",
        "pcb footprint",
        "package/case",
        "package / case",
        "footprint/package",
        "encapsulation",
    }
)

_ANY_HEADER: Final[frozenset[str]] = (
    _MPN_HEADERS | _QTY_HEADERS | _MANUFACTURER_HEADERS | _REFERENCE_HEADERS | _VALUE_HEADERS | _FOOTPRINT_HEADERS
)

_SEVERITY_ORDER: Final[dict[RiskSeverity, int]] = {
    RiskSeverity.INFO: 0,
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}

logger = logging.getLogger(__name__)

_NORMALISE_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

_COMPANY_ALIASES: Final[dict[str, str]] = {
    "ti": "texasinstruments",
    "st": "stmicroelectronics",
    "stm": "stmicroelectronics",
    "ir": "internationalrectifier",
    "infineon": "infineontechnologies",
    "adi": "analogdevices",
    "maxim": "analogdevices",
    "diodes": "diodesincorporated",
    "microchip": "microchiptechnology",
    "on": "onsemi",
    "aos": "alphaomegasemiconductor",
    "vishay": "vishaysiliconix",
    "renesas": "renesaselectronics",
    "nexperia": "nexperia",
}

_PACKAGING_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:-?(?:TR|T&R|TAPE|REEL|RL|PBF|PB-FREE|NOPB|REEL7|REEL13|TUBE|\+|#PBF|\bATMA1\b|\bAMNTWG\b))+$",
    re.IGNORECASE,
)


def _clean_footprint(raw: str | None) -> str:
    """Normalize EDA footprint strings (e.g. 'Package_TO_SOT_THT:TO-220-3_Vertical' -> 'TO-220')."""
    if not raw or not str(raw).strip():
        return ""
    text = str(raw).strip()
    if ":" in text:
        text = text.split(":", 1)[1]
    match = re.search(
        r"\b(TO-?220|TO-?263|TO-?252|TO-?247|TO-?92|D2PAK|DPAK|SUPERSO8|SUPER-?SO8|POWERPAK\s*SO-8|SOIC-?(?:8|14|16|20|28)|SO-?(?:8|14|16|20|28)|DIP-?(?:4|8|14|16|28)|QFN-?\d+|DFN-?\d+|LQFP-?\d+|TSSOP-?\d+|SOT-?(?:23|223)(?:-\d+)?|DO-?(?:35|41)|SMA|SMB|SMC|0402|0603|0805|1206|1210)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        pkg = match.group(1).upper()
        if "TO220" in pkg and "TO-220" not in pkg:
            pkg = pkg.replace("TO220", "TO-220")
        return pkg
    cleaned = re.sub(r"_[a-zA-Z0-9]*metric\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"_(?:vertical|horizontal|angled|smd|tht|thermalpad)\b", "", cleaned, flags=re.IGNORECASE)
    return cleaned.replace("_", " ").strip().upper()


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
    a = _COMPANY_ALIASES.get(a, a)
    b = _COMPANY_ALIASES.get(b, b)
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
        web_discovery: Any | None = None,
        query_planner: Any | None = None,
        provider_discovery: Any | None = None,
        advisor: Any | None = None,
        max_live_lines: int = 50,
    ) -> None:
        self._repository = repository
        self._low_stock_threshold = int(low_stock_threshold)
        self._single_source_max = int(single_source_max)
        self._web_discovery = web_discovery
        self._query_planner = query_planner
        self._provider_discovery = provider_discovery
        self._advisor = advisor
        self._max_live_lines = max(0, int(max_live_lines))
        self._live_queries: list[str] = []
        self._live_discovered = 0

    # -- parsing ----------------------------------------------------------------

    @staticmethod
    def _detect_delimiter(sample: str) -> str:
        """Return the delimiter of the CSV (``","``, ``";"``, tab, or ``"|"``)."""
        lines = [
            line.strip()
            for line in sample.splitlines()
            if line.strip() and not line.strip().startswith(("#", "//", "/*", ";;"))
        ]
        if not lines:
            return ","
        clean_sample = "\n".join(lines[:10])
        try:
            dialect = csv.Sniffer().sniff(clean_sample, delimiters=",;\t|")
            if dialect.delimiter:
                return dialect.delimiter
        except (csv.Error, TypeError):
            pass

        counts = {",": 0, ";": 0, "\t": 0, "|": 0}
        for line in lines[:5]:
            counts[","] += line.count(",")
            counts[";"] += line.count(";")
            counts["\t"] += line.count("\t")
            counts["|"] += line.count("|")
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
                clean_row = [str(cell).strip() for cell in row]
                if clean_row and any(c for c in clean_row):
                    if clean_row[0].startswith(("#", "//", "/*")):
                        continue
                    rows.append(clean_row)
        except csv.Error:
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str or line_str.startswith(("#", "//")):
                    continue
                rows.append([cell.strip() for cell in line.split(delimiter)])
        return rows

    @staticmethod
    def _detect_columns(header: list[str]) -> dict[str, int]:
        """Return the column indexes of the known header names with strict priority."""
        columns: dict[str, int] = {}
        normalised_headers = [_normalise_header(cell) for cell in header]

        # 1. High-priority explicit MPN headers
        explicit_mpn_headers = {
            "mpn",
            "mpn/part number",
            "part number",
            "partnumber",
            "part no",
            "part no.",
            "part_number",
            "part-number",
            "part #",
            "part#",
            "pn",
            "p/n",
            "p.n.",
            "pn/part number",
            "manufacturer part number",
            "manufacturer part no",
            "manufacturer part no.",
            "mfr part number",
            "mfr part no",
            "mfr. part number",
            "mfr. part no.",
            "mfr part #",
            "mfr part",
            "mfr pn",
            "mfg part number",
            "mfg part no",
            "mfg part #",
            "component",
            "component name",
            "component part number",
            "device",
            "order code",
            "ordering code",
            "lcsc part #",
            "lcsc part number",
            "digikey part number",
            "digi-key part number",
            "mouser part number",
        }

        for index, name in enumerate(normalised_headers):
            if name in explicit_mpn_headers and "mpn" not in columns:
                columns["mpn"] = index
            elif name in _QTY_HEADERS and "qty" not in columns:
                columns["qty"] = index
            elif name in _MANUFACTURER_HEADERS and "manufacturer" not in columns:
                columns["manufacturer"] = index
            elif name in _REFERENCE_HEADERS and "reference" not in columns:
                columns["reference"] = index
            elif name in _FOOTPRINT_HEADERS and "footprint" not in columns:
                columns["footprint"] = index
            elif name in _VALUE_HEADERS and "value" not in columns:
                columns["value"] = index

        # 2. Secondary fallback for MPN: value, comment, part, designation
        if "mpn" not in columns:
            if "value" in columns:
                columns["mpn"] = columns["value"]
            else:
                secondary_mpn_headers = {
                    "part",
                    "part name",
                    "value",
                    "val",
                    "comment",
                    "designation",
                    "article",
                    "catalog no",
                    "catalog number",
                    "item",
                    "item number",
                }
                for index, name in enumerate(normalised_headers):
                    if name in secondary_mpn_headers and index not in columns.values():
                        columns["mpn"] = index
                        break

        return columns

    @staticmethod
    def _is_header(row: list[str]) -> bool:
        return any(_normalise_header(cell) in _ANY_HEADER for cell in row)

    @staticmethod
    def _to_quantity(cell: str) -> int:
        clean = (cell or "").strip()
        clean = re.sub(r"(?i)\s*(?:pcs|pieces|units|x)$", "", clean)
        try:
            value = float(clean.replace(",", "."))
        except (TypeError, ValueError):
            return 1
        if value <= 0:
            return 1
        return int(value)

    # -- matching ---------------------------------------------------------------

    def _find_part(self, mpn: str) -> PartRecord | None:
        """Match one MPN against the repository with multi-tier normalized matching."""
        if not mpn or not mpn.strip():
            return None
        clean = mpn.strip()

        # 1. Exact match
        part = self._repository.get_part_by_mpn(clean)
        if part is not None:
            return part

        # 2. Case-insensitive exact or substring match
        try:
            summaries, _ = self._repository.list_parts(
                SearchFilter(mpn_contains=clean), limit=25, offset=0
            )
            for s in summaries:
                if (s.mpn or "").strip().lower() == clean.lower():
                    found = self._repository.get_part(s.part_id)
                    if found is not None:
                        return found
            if summaries:
                found = self._repository.get_part(summaries[0].part_id)
                if found is not None:
                    return found
        except Exception:
            pass

        # 3. Stem / packaging suffix stripped match
        stem = _PACKAGING_SUFFIX_RE.sub("", clean).strip("-_./+ ")
        if stem and stem.lower() != clean.lower():
            part = self._repository.get_part_by_mpn(stem)
            if part is not None:
                return part
            try:
                summaries, _ = self._repository.list_parts(
                    SearchFilter(mpn_contains=stem), limit=25, offset=0
                )
                for s in summaries:
                    s_stem = _PACKAGING_SUFFIX_RE.sub("", s.mpn).strip("-_./+ ")
                    if s_stem.lower() == stem.lower() or s.mpn.lower() == stem.lower():
                        found = self._repository.get_part(s.part_id)
                        if found is not None:
                            return found
                if summaries:
                    found = self._repository.get_part(summaries[0].part_id)
                    if found is not None:
                        return found
            except Exception:
                pass

        return None

    def _enrich_bom_parts(self, rows: list[Any]) -> None:
        """Run bounded multi-tier live discovery using Value, Footprint, and MPN concurrently at scale."""
        # Only run if at least one discovery backend is explicitly configured
        if (
            self._advisor is None
            and self._web_discovery is None
            and self._provider_discovery is None
        ):
            return

        self._live_queries = []
        self._live_discovered = 0
        seen: set[str] = set()
        unmatched_jobs: list[dict[str, Any]] = []

        for item in rows[: self._max_live_lines]:
            if isinstance(item, dict):
                mpn = (item.get("mpn") or "").strip()
                val = (item.get("value") or "").strip()
                fp = (item.get("footprint") or "").strip()
                mfr = (item.get("manufacturer") or "").strip() if item.get("manufacturer") else None
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                mpn = str(item[0] or "").strip()
                val = mpn
                fp = ""
                mfr = str(item[1] or "").strip() if item[1] else None
            else:
                continue

            target = mpn or val
            if not target:
                continue
            if target.upper().startswith(("UNKNOWN", "NO-SUCH", "NONE", "N/A", "DUMMY", "NOT-FOUND")):
                continue

            clean_fp = _clean_footprint(fp)
            key = f"{target.lower()}::{clean_fp.lower()}"
            if key in seen:
                continue
            seen.add(key)

            if self._find_part(target) is not None:
                continue

            unmatched_jobs.append({
                "mpn": mpn,
                "value": val,
                "footprint": fp,
                "clean_footprint": clean_fp,
                "manufacturer": mfr,
            })

        if not unmatched_jobs:
            return

        if self._query_planner is not None:
            for job in unmatched_jobs:
                target = job.get("mpn") or job.get("value") or ""
                fp = job.get("clean_footprint") or ""
                target_with_fp = f"{target} {fp}".strip() if fp else target
                queries = self._query_planner.plan(target_with_fp, job.get("manufacturer"))
                self._live_queries.extend(queries)

        def discover_one(job: dict[str, Any]) -> int:
            val = job.get("value") or job.get("mpn") or ""
            clean_fp = job.get("clean_footprint") or ""
            mfr = (job.get("manufacturer") or "").strip()
            mfr_str = f"{mfr} " if mfr else ""

            # 1. Try ComponentAdvisorService (Instant template catalog + LLM dynamic discovery)
            advisor = self._advisor
            if advisor is not None:
                try:
                    query = f"{val} {clean_fp}".strip() if clean_fp else val
                    records = advisor.discover_and_ingest(query)
                    if not records and clean_fp:
                        records = advisor.discover_and_ingest(val)
                    if records:
                        return len(records)
                except Exception as exc:
                    logger.debug("BOM advisor discovery failed for %s: %s", val, exc)

            # 2. Try WebDiscoveryService (SearXNG live search with value + footprint!)
            if self._web_discovery is not None:
                try:
                    query = f"{mfr_str}{val} {clean_fp} datasheet".strip() if clean_fp else f"{mfr_str}{val} datasheet".strip()
                    records, _ = self._web_discovery.discover_and_ingest_with_results(query, limit=5)
                    if not records and clean_fp:
                        records, _ = self._web_discovery.discover_and_ingest_with_results(f"{mfr_str}{val} datasheet".strip(), limit=5)
                    if records:
                        return len(records)
                except Exception as exc:
                    logger.debug("BOM web discovery failed for %s: %s", val, exc)

            # 3. Try ProviderDiscoveryService (DigiKey, Mouser, Nexar live APIs)
            if self._provider_discovery is not None:
                try:
                    query = f"{val} {clean_fp}".strip() if clean_fp else val
                    records = self._provider_discovery.discover_and_ingest(query, limit=5)
                    if not records and clean_fp:
                        records = self._provider_discovery.discover_and_ingest(val, limit=5)
                    if records:
                        return len(records)
                except Exception as exc:
                    logger.debug("BOM provider discovery failed for %s: %s", val, exc)

            return 0

        with ThreadPoolExecutor(max_workers=min(6, len(unmatched_jobs) or 1)) as pool:
            results = list(pool.map(discover_one, unmatched_jobs))
            self._live_discovered = sum(results)

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

        # Locate header row among first 10 rows
        header_row_index = -1
        columns: dict[str, int] = {}
        for r_idx, row in enumerate(rows[:10]):
            cols = self._detect_columns(row)
            if "mpn" in cols or len(cols) >= 2 or self._is_header(row):
                header_row_index = r_idx
                columns = cols
                break

        has_header = header_row_index != -1
        data_rows = rows[header_row_index + 1 :] if has_header else rows
        reference_index = columns.get("reference")
        qty_index = columns.get("qty")
        manufacturer_index = columns.get("manufacturer")
        footprint_index = columns.get("footprint")
        value_index = columns.get("value")

        if "mpn" in columns:
            mpn_index = columns["mpn"]
        elif value_index is not None:
            mpn_index = value_index
        else:
            taken = {idx for idx in (reference_index, qty_index, manufacturer_index, footprint_index, value_index) if idx is not None}
            available = [i for i in range(len(rows[0])) if i not in taken]
            mpn_index = available[0] if available else 0

        lines: list[BomLine] = []
        all_risks: list[BomRisk] = []
        matched_lines = 0
        highest: RiskSeverity | None = None

        enrich_payload = []
        for row in data_rows:
            r_mpn = row[mpn_index].strip() if mpn_index < len(row) else ""
            r_val = row[value_index].strip() if value_index is not None and value_index < len(row) else r_mpn
            r_fp = row[footprint_index].strip() if footprint_index is not None and footprint_index < len(row) else None
            r_mfr = row[manufacturer_index].strip() if manufacturer_index is not None and manufacturer_index < len(row) else None
            enrich_payload.append({
                "mpn": r_mpn,
                "value": r_val,
                "footprint": r_fp,
                "manufacturer": r_mfr,
            })

        self._enrich_bom_parts(enrich_payload)

        for offset, row in enumerate(data_rows):
            line_number = offset + (header_row_index + 2 if has_header else 1)
            mpn = row[mpn_index].strip() if mpn_index < len(row) else ""
            value = row[value_index].strip() if value_index is not None and value_index < len(row) else mpn
            footprint = row[footprint_index].strip() if footprint_index is not None and footprint_index < len(row) else None
            clean_fp = _clean_footprint(footprint)
            target = mpn or value

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
            part = self._find_part(target) if target else None
            if part is None and value and value != mpn:
                part = self._find_part(value)

            if part is None:
                risks.append(
                    BomRisk(
                        code="not_found",
                        severity=RiskSeverity.HIGH,
                        message=(
                            f"No part matches '{target}'" if target else "The line has no part number or value"
                        ),
                        mpn=target or None,
                        suggestion="Check the part number, value, and footprint.",
                    )
                )
            else:
                matched_lines += 1
                risks.extend(self._risks_for(part, manufacturer))
                if clean_fp and part.package:
                    part_pkg_clean = _clean_footprint(part.package)
                    if clean_fp not in part_pkg_clean and part_pkg_clean not in clean_fp:
                        risks.append(
                            BomRisk(
                                code="footprint_mismatch",
                                severity=RiskSeverity.INFO,
                                message=f"BOM footprint '{clean_fp}' differs from part package '{part.package}'",
                                part_id=part.part_id,
                                mpn=part.mpn,
                                suggestion="Verify PCB pad layout and physical dimensions against datasheet.",
                            )
                        )

            for risk in risks:
                if highest is None or _SEVERITY_ORDER[risk.severity] > _SEVERITY_ORDER[highest]:
                    highest = risk.severity
            all_risks.extend(risks)

            lines.append(
                BomLine(
                    line_number=line_number,
                    mpn=target,
                    quantity=quantity,
                    manufacturer=manufacturer or (part.manufacturer if part else None),
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
            live_queries=list(dict.fromkeys(self._live_queries)),
            live_discovered=self._live_discovered,
        )
