"""Fake service layer.

The services of the plan (WP6) are implemented by agent F. Until they land the
API uses these implementations, which follow the protocols of
``shared.interfaces`` exactly, so the real ones can be dropped in without
touching a route.

No network, no LLM, no real distributor data.
"""

from __future__ import annotations

import csv
import io
import re
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.fakes.llm import StubLLMExtractor
from services.search import fallback_filter
from shared.schemas import (
    AlternativeResult,
    BomCheckResponse,
    BomLine,
    BomRisk,
    JobKind,
    JobRequest,
    JobState,
    JobStatus,
    LifecycleStatus,
    PartRecord,
    ReviewDecision,
    ReviewItem,
    ReviewResponse,
    RiskSeverity,
    SearchFilter,
    SearchResponse,
    StatsResponse,
)

_SEVERITY_ORDER = {
    RiskSeverity.INFO: 0,
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}

_MPN_COLUMNS = (
    "mpn",
    "partnumber",
    "manufacturerpartnumber",
    "mfrpartnumber",
    "mfgpartnumber",
    "pn",
    "partno",
    "part",
    "component",
    "device",
    "value",
    "val",
    "comment",
    "item",
    "ordercode",
    "article",
)
_QTY_COLUMNS = (
    "quantity",
    "qty",
    "count",
    "qnt",
    "amount",
    "pcs",
    "units",
    "totalqty",
)
_REF_COLUMNS = (
    "reference",
    "references",
    "ref",
    "refdes",
    "designator",
    "designators",
    "location",
    "loc",
)
_MANUFACTURER_COLUMNS = (
    "manufacturer",
    "mfr",
    "mfrname",
    "brand",
    "make",
    "vendor",
    "producer",
    "company",
)


def _normalise_header(name: str) -> str:
    """Normalise a CSV header so ``Mfr Part Number`` becomes ``mfrpartnumber``."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _pick_column(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    """Return the first header that matches one of the candidate names.

    ``headers`` holds the *original* header names; they are compared with
    their normalised form so ``Mfr Part Number`` matches ``mfrpartnumber``.
    """
    normalised = [_normalise_header(header) for header in headers]
    for candidate in candidates:
        for header, name in zip(headers, normalised, strict=False):
            if name == candidate:
                return header
    for candidate in candidates:
        for header, name in zip(headers, normalised, strict=False):
            if candidate in name:
                return header
    return None


class FakeSearchService:
    """Filter and free-text search over the repository."""

    def __init__(self, repository: Any, llm_extractor: Any | None = None) -> None:
        self._repo = repository
        self._llm = llm_extractor or StubLLMExtractor()

    def search(self, query: str, limit: int = 50, offset: int = 0) -> SearchResponse:
        """Build a filter from ``query`` and execute it."""
        filt = self._llm.build_search_filter(query)
        deterministic = fallback_filter(query)
        if filt == SearchFilter() and deterministic != SearchFilter():
            filt = deterministic
        response = self.search_filter(filt, limit=limit, offset=offset)
        response.query = query
        response.llm_used = filt != deterministic
        response.filter_explanation = self._explain(filt)
        return response

    def search_filter(self, filt: SearchFilter, limit: int = 50, offset: int = 0) -> SearchResponse:
        """Execute an already validated filter."""
        started = time.perf_counter()
        rows, total = self._repo.list_parts(filt, limit, offset)
        took_ms = int((time.perf_counter() - started) * 1000)
        return SearchResponse(
            query=None,
            filter=filt,
            results=rows,
            total=total,
            limit=limit,
            offset=offset,
            took_ms=took_ms,
            llm_used=False,
        )

    @staticmethod
    def _explain(filt: SearchFilter) -> str:
        """A short, human readable description of the executed filter."""
        parts: list[str] = []
        if filt.family:
            parts.append(f"family={filt.family.value}")
        if filt.manufacturer:
            parts.append(f"manufacturer={filt.manufacturer}")
        if filt.package:
            parts.append(f"package={filt.package}")
        if filt.lifecycle_status:
            parts.append("lifecycle=" + ",".join(item.value for item in filt.lifecycle_status))
        if filt.in_stock is not None:
            parts.append(f"in_stock={filt.in_stock}")
        if filt.text:
            parts.append(f"text~{filt.text}")
        for constraint in filt.parameters:
            bound = constraint.max if constraint.max is not None else constraint.min
            parts.append(f"{constraint.name}{constraint.operator}{bound}{constraint.unit or ''}")
        return " AND ".join(parts) if parts else "no filter"


class FakeAlternativesService:
    """Ranks the parts of the same family by parameter similarity."""

    def __init__(self, repository: Any, llm_extractor: Any | None = None) -> None:
        self._repo = repository
        self._llm = llm_extractor or StubLLMExtractor()

    def alternatives(
        self,
        part_id: str,
        limit: int = 10,
        explain: bool = True,
    ) -> list[AlternativeResult]:
        """Return ranked alternatives for ``part_id``."""
        part = self._repo.get_part(part_id)
        if part is None:
            raise KeyError(part_id)
        summaries, _ = self._repo.list_parts(SearchFilter(family=part.family), limit=500, offset=0)
        results: list[AlternativeResult] = []
        for summary in summaries:
            if summary.part_id == part_id:
                continue
            candidate = self._repo.get_part(summary.part_id)
            if candidate is None:
                continue
            differences = _differences(part, candidate)
            score = _score(part, candidate, differences)
            rejected = candidate.lifecycle_status == LifecycleStatus.OBSOLETE
            reason = _reason(part, candidate, differences)
            if explain:
                reason = self._llm.explain_alternative(differences, candidate.mpn)
            results.append(
                AlternativeResult(
                    part=summary,
                    score=round(score, 2),
                    rank=0,
                    reason=reason,
                    rejected=rejected,
                    rejection_reason="The part is obsolete." if rejected else None,
                    differences=differences,
                )
            )
        results.sort(key=lambda item: (item.rejected, -item.score, item.part.mpn))
        for index, item in enumerate(results[:limit], start=1):
            item.rank = index
        return results[:limit]


def _differences(part: PartRecord, candidate: PartRecord) -> dict[str, dict[str, float | None]]:
    """Compare the parameter values of two parts."""
    source = {value.name: value.representative() for value in part.parameters}
    target = {value.name: value.representative() for value in candidate.parameters}
    differences: dict[str, dict[str, float | None]] = {}
    for name, value in source.items():
        if name not in target:
            continue
        other = target[name]
        if value is None or other is None:
            continue
        if abs(value - other) < 1e-12:
            continue
        differences[name] = {"source": value, "candidate": other}
    return differences


def _score(part: PartRecord, candidate: PartRecord, differences: dict[str, Any]) -> float:
    """A similarity score between 0 and 100."""
    score = 100.0
    for value in differences.values():
        source = value.get("source") or 0.0
        other = value.get("candidate") or 0.0
        reference = max(abs(source), abs(other), 1e-9)
        score -= min(40.0, 100.0 * abs(source - other) / reference)
    if part.package and candidate.package and part.package != candidate.package:
        score -= 10.0
    if part.lifecycle_status != candidate.lifecycle_status:
        score -= 5.0
    return max(0.0, min(100.0, score))


def _reason(part: PartRecord, candidate: PartRecord, differences: dict[str, Any]) -> str:
    """A short reason why the candidate is an alternative."""
    parts = [f"same family ({part.family.value})"]
    if part.package and candidate.package == part.package:
        parts.append(f"same package ({part.package})")
    if differences:
        parts.append(f"{len(differences)} parameter(s) differ")
    return ", ".join(parts)


class FakeBomService:
    """Parses a BOM CSV and reports the risk of every line."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def check_csv(self, content: str, filename: str | None = None) -> BomCheckResponse:
        """Parse a BOM CSV and return the risk table."""
        started = time.perf_counter()
        text = content or ""
        if text.startswith("\ufeff"):
            text = text[1:]
        lines: list[BomLine] = []
        risks: list[BomRisk] = []

        reader = _make_reader(text)
        if reader is None:
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

        headers = list(reader.fieldnames or [])
        mpn_column = _pick_column(headers, _MPN_COLUMNS)
        qty_column = _pick_column(headers, _QTY_COLUMNS)
        ref_column = _pick_column(headers, _REF_COLUMNS)
        manufacturer_column = _pick_column(headers, _MANUFACTURER_COLUMNS)
        if mpn_column is None:
            raise ValueError("The CSV needs a column with the manufacturer part number.")

        for number, row in enumerate(reader, start=2):
            mpn = (row.get(mpn_column) or "").strip()
            if not mpn:
                continue
            quantity = 1
            if qty_column:
                try:
                    quantity = int(float(row.get(qty_column) or 1))
                except ValueError:
                    quantity = 1
            part = self._repo.get_part_by_mpn(mpn)
            if part is None:
                stem = re.sub(r"(?:-?(?:TR|T&R|PBF|NOPB|\+))+$", "", mpn, flags=re.IGNORECASE).strip()
                if stem and stem.lower() != mpn.lower():
                    part = self._repo.get_part_by_mpn(stem)
            line_risks: list[BomRisk] = []
            if part is None:
                line_risks.append(
                    BomRisk(
                        code="not_found",
                        severity=RiskSeverity.HIGH,
                        message=f"{mpn} was not found in the catalogue.",
                        mpn=mpn,
                        suggestion="Check the spelling or add the part to the catalogue.",
                    )
                )
            else:
                line_risks.extend(self._risks_for_part(part))
            risks.extend(line_risks)
            lines.append(
                BomLine(
                    line_number=number,
                    mpn=mpn,
                    quantity=quantity,
                    manufacturer=(
                        (row.get(manufacturer_column) or None) if manufacturer_column else None
                    ),
                    reference=(row.get(ref_column) or None) if ref_column else None,
                    matched_part_id=part.part_id if part else None,
                    matched=part is not None,
                    risks=line_risks,
                )
            )

        matched = sum(1 for line in lines if line.matched)
        highest = None
        for risk in risks:
            if highest is None or _SEVERITY_ORDER[risk.severity] > _SEVERITY_ORDER[highest]:
                highest = risk.severity
        return BomCheckResponse(
            filename=filename,
            total_lines=len(lines),
            matched_lines=matched,
            unmatched_lines=len(lines) - matched,
            risk_count=len(risks),
            highest_severity=highest,
            lines=lines,
            risks=risks,
            took_ms=int((time.perf_counter() - started) * 1000),
        )

    def _risks_for_part(self, part: PartRecord) -> list[BomRisk]:
        """The risks of one known part."""
        risks: list[BomRisk] = []
        if part.lifecycle_status == LifecycleStatus.OBSOLETE:
            risks.append(
                BomRisk(
                    code="obsolete",
                    severity=RiskSeverity.CRITICAL,
                    message=f"{part.mpn} is obsolete.",
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Replace the part with a supported alternative.",
                )
            )
        elif part.lifecycle_status == LifecycleStatus.NRND:
            risks.append(
                BomRisk(
                    code="nrnd",
                    severity=RiskSeverity.MEDIUM,
                    message=f"{part.mpn} is not recommended for new designs (NRND).",
                    part_id=part.part_id,
                    mpn=part.mpn,
                    suggestion="Plan a migration to an active part.",
                )
            )
        offers = part.offers
        if not offers:
            risks.append(
                BomRisk(
                    code="no_offers",
                    severity=RiskSeverity.HIGH,
                    message=f"{part.mpn} has no distributor offer.",
                    part_id=part.part_id,
                    mpn=part.mpn,
                )
            )
        elif len(offers) == 1:
            risks.append(
                BomRisk(
                    code="single_source",
                    severity=RiskSeverity.LOW,
                    message=f"{part.mpn} is only available at one distributor.",
                    part_id=part.part_id,
                    mpn=part.mpn,
                )
            )
        if offers and all(not offer.stock for offer in offers):
            risks.append(
                BomRisk(
                    code="out_of_stock",
                    severity=RiskSeverity.MEDIUM,
                    message=f"{part.mpn} is out of stock at every distributor.",
                    part_id=part.part_id,
                    mpn=part.mpn,
                )
            )
        return risks


def _make_reader(text: str) -> csv.DictReader | None:
    """Build a CSV reader, sniffing the delimiter."""
    if not text.strip():
        return None
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(io.StringIO(text), dialect=dialect)


class FakeReviewService:
    """The review queue of the repository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def queue(self, limit: int = 50, offset: int = 0) -> list[ReviewItem]:
        """Return the review queue."""
        return self._repo.list_review_queue(limit=limit, offset=offset)

    def decide(self, param_id: str, decision: ReviewDecision) -> ReviewResponse:
        """Apply a human decision to one reviewed value."""
        try:
            return self._repo.apply_review(param_id, decision)
        except KeyError as exc:
            raise KeyError(param_id) from exc


class FakeStatsService:
    """The dashboard numbers of the repository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def stats(self) -> StatsResponse:
        """Return counts and quality numbers."""
        return self._repo.stats()


class FakeJobRunner:
    """An in-memory job runner.

    ``submit`` only queues the job; the work happens in ``run`` which the API
    calls from a background task.
    """

    def __init__(self, repository: Any, tier1_extractor: Any | None = None) -> None:
        self._repo = repository
        self._tier1 = tier1_extractor
        self._jobs: dict[str, JobStatus] = {}
        self._requests: dict[str, JobRequest] = {}

    def submit(self, request: JobRequest) -> JobStatus:
        """Queue a job and return its initial status."""
        now = datetime.now(UTC)
        status = JobStatus(
            job_id=f"job-{uuid4().hex[:12]}",
            kind=JobKind.EXTRACT,
            state=JobState.QUEUED,
            progress=0,
            total=1,
            message="Queued",
            part_id=request.part_id,
            source_id=request.source_id,
            created_at=now,
            updated_at=now,
        )
        self._jobs[status.job_id] = status
        self._requests[status.job_id] = request
        return status

    def get(self, job_id: str) -> JobStatus | None:
        """Return the current status of a job."""
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[JobStatus]:
        """Return recent jobs, newest first."""
        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return jobs[:limit]

    def run(self, job_id: str) -> JobStatus | None:
        """Execute the work of a job (called from the background task)."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        request = self._requests.get(job_id, JobRequest())
        job.state = JobState.RUNNING
        job.message = "Running"
        job.updated_at = datetime.now(UTC)
        try:
            result: dict[str, Any] = {}
            if request.pdf_path and self._tier1 is not None:
                extraction = self._tier1.extract(request.pdf_path, request.family)
                result = {
                    "values": len(extraction.values),
                    "failed_fields": list(extraction.failed_fields),
                    "pages_used": list(extraction.pages_used),
                    "method": extraction.method.value,
                }
                job.total = len(extraction.values)
                job.progress = len(extraction.values)
            else:
                job.message = "Nothing to extract - no PDF was given."
            job.result = result
            job.state = JobState.COMPLETED
            job.message = job.message if "Nothing" in job.message else "Completed"
        except Exception as exc:  # pragma: no cover - defensive
            job.state = JobState.FAILED
            job.error = type(exc).__name__
            job.message = "Failed"
        job.updated_at = datetime.now(UTC)
        return job


__all__ = [
    "FakeAlternativesService",
    "FakeBomService",
    "FakeJobRunner",
    "FakeReviewService",
    "FakeSearchService",
    "FakeStatsService",
]
