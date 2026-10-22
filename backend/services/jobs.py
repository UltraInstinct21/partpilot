"""Background extraction jobs (plan WP6, WP2 "do not block a request").

``submit`` returns immediately with ``state=queued``; the work runs later on a
FastAPI ``BackgroundTasks`` object (when one is injected) or on a daemon
thread. The job registry lives **in memory** - it is not persisted, so a
restart loses the history (documented in ``HANDOFF.md``).

The job pipeline is the tier rule of the plan:

1. tier 1 (rule based) runs first;
2. when tier 1 fails and an LLM extractor is injected, tier 2 runs over the page
   text - the LLM never invents a value, it only reads the text;
3. every value is validated by the injected validator;
4. the values are stored through the injected repository.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from shared.interfaces import LLMExtractor, PartsRepository, Tier1Extractor, Validator
from shared.schemas import (
    ExtractionResult,
    Family,
    JobKind,
    JobRequest,
    JobState,
    JobStatus,
    PartRecord,
)

__all__ = ["BackgroundJobRunner"]

PagesProvider = Callable[[str], list[tuple[int, str]]]


class BackgroundJobRunner:
    """Run extraction jobs in the background and track their progress.

    Args:
        repository: the injected :class:`~shared.interfaces.PartsRepository`.
        tier1: the injected :class:`~shared.interfaces.Tier1Extractor`.
        llm: optional :class:`~shared.interfaces.LLMExtractor` used when tier 1
            fails.
        validator: optional :class:`~shared.interfaces.Validator`.
        background_tasks: an optional FastAPI ``BackgroundTasks`` instance. When
            it is given, the job is scheduled on it; otherwise a daemon thread
            is used.
        pages_provider: optional callable ``(pdf_path) -> [(page, text)]`` used
            for the tier 2 fallback. When it is missing, the text is read with
            ``pdfplumber`` if it is installed.
        max_jobs: how many job states are kept in memory.
    """

    def __init__(
        self,
        repository: PartsRepository,
        tier1: Tier1Extractor | None = None,
        llm: LLMExtractor | None = None,
        validator: Validator | None = None,
        *,
        background_tasks: Any | None = None,
        pages_provider: PagesProvider | None = None,
        max_jobs: int = 200,
    ) -> None:
        self._repository = repository
        self._tier1 = tier1
        self._llm = llm
        self._validator = validator
        self._background_tasks = background_tasks
        self._pages_provider = pages_provider
        self._max_jobs = max(1, int(max_jobs))
        self._jobs: dict[str, JobStatus] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    # -- registry ---------------------------------------------------------------

    def _remember(self, status: JobStatus) -> None:
        with self._lock:
            self._jobs[status.job_id] = status
            self._order.append(status.job_id)
            while len(self._order) > self._max_jobs:
                old = self._order.pop(0)
                self._jobs.pop(old, None)

    def _update(self, job_id: str, **changes: Any) -> JobStatus | None:
        with self._lock:
            status = self._jobs.get(job_id)
            if status is None:
                return None
            for key, value in changes.items():
                setattr(status, key, value)
            status.updated_at = datetime.now(UTC)
            return status

    # -- protocol ---------------------------------------------------------------

    def submit(self, request: JobRequest) -> JobStatus:
        """Queue a job and return its initial status (``state=queued``)."""
        job_id = uuid.uuid4().hex
        status = JobStatus(
            job_id=job_id,
            kind=JobKind.EXTRACT,
            state=JobState.QUEUED,
            progress=0,
            total=0,
            message="queued",
            part_id=request.part_id,
            source_id=request.source_id,
        )
        self._remember(status)
        # Take the snapshot before the work starts: the worker may already
        # have changed the state when the copy is made.
        snapshot = status.model_copy(deep=True)
        self._schedule(job_id, request)
        return snapshot

    def get(self, job_id: str) -> JobStatus | None:
        """Return the current status of a job."""
        with self._lock:
            status = self._jobs.get(job_id)
            return status.model_copy(deep=True) if status is not None else None

    def list(self, limit: int = 50) -> list[JobStatus]:
        """Return the recent jobs, newest first."""
        with self._lock:
            job_ids = list(reversed(self._order))
        count = max(0, int(limit))
        result: list[JobStatus] = []
        for job_id in job_ids:
            if len(result) >= count:
                break
            status = self.get(job_id)
            if status is not None:
                result.append(status)
        return result

    # -- scheduling -------------------------------------------------------------

    def _schedule(self, job_id: str, request: JobRequest) -> None:
        tasks = self._background_tasks
        if tasks is not None and hasattr(tasks, "add_task"):
            tasks.add_task(self.run_job, job_id, request)
            return
        thread = threading.Thread(
            target=self.run_job,
            args=(job_id, request),
            name=f"partpilot-job-{job_id[:8]}",
            daemon=True,
        )
        thread.start()

    def run_job(self, job_id: str, request: JobRequest) -> JobStatus:
        """Run one job. This is the callable the background task executes."""
        try:
            self._update(job_id, state=JobState.RUNNING, progress=10, message="reading the PDF")
            result = self._extract(request)
            self._update(job_id, progress=60, message="validating the values")
            values = self._validate(result)
            self._update(job_id, progress=80, message="storing the values")
            stored = self._store(request, result, values)
            payload: dict[str, Any] = {
                "part_id": stored.part_id if stored else request.part_id,
                "values": len(values),
                "failed_fields": list(result.failed_fields),
                "pages_used": list(result.pages_used),
                "method": result.method.value if result.method else None,
                "source_id": result.source_id or request.source_id,
            }
            status = self._update(
                job_id,
                state=JobState.COMPLETED,
                progress=100,
                total=len(values),
                message="done",
                result=payload,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 - the job must never crash the server
            status = self._update(
                job_id,
                state=JobState.FAILED,
                message=f"failed: {exc}",
                error=str(exc),
            )
        return status if status is not None else JobStatus(job_id=job_id, state=JobState.FAILED)

    # -- the pipeline -----------------------------------------------------------

    def _extract(self, request: JobRequest) -> ExtractionResult:
        """Run tier 1 and fall back to tier 2 when tier 1 fails."""
        if not request.pdf_path:
            raise ValueError("pdf_path is required")
        tier1_error: Exception | None = None
        result: ExtractionResult | None = None
        if self._tier1 is not None:
            try:
                result = self._tier1.extract(request.pdf_path, request.family)
            except Exception as exc:  # noqa: BLE001 - tier 1 may fail on any PDF
                tier1_error = exc
                result = None
        if result is None or not result.values:
            if self._llm is None:
                if tier1_error is not None:
                    raise RuntimeError(f"tier 1 extraction failed: {tier1_error}") from tier1_error
                raise RuntimeError("tier 1 returned no values")
            pages = self._pages(request.pdf_path)
            family = request.family or Family.MOSFET
            result = self._llm.extract_tier2(pages, family, request.part_id)
        return result

    def _pages(self, pdf_path: str) -> list[tuple[int, str]]:
        """Return the page text used by the tier 2 fallback."""
        if self._pages_provider is not None:
            return list(self._pages_provider(pdf_path))
        try:
            import pdfplumber
        except ImportError:  # pragma: no cover - pdfplumber is a hard dependency
            return []
        pages: list[tuple[int, str]] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for number, page in enumerate(pdf.pages, start=1):
                    pages.append((number, page.extract_text() or ""))
        except Exception:  # pragma: no cover - a broken PDF must not crash the job
            return []
        return pages

    def _validate(self, result: ExtractionResult) -> list[Any]:
        """Validate every extracted value."""
        values: list[Any] = []
        for value in result.values:
            if self._validator is not None:
                values.append(self._validator.validate(value))
            else:
                values.append(value)
        return values

    def _store(
        self, request: JobRequest, result: ExtractionResult, values: Iterable[Any]
    ) -> PartRecord | None:
        """Store the validated values through the repository."""
        values = list(values)
        if not request.part_id:
            return None
        part = self._repository.get_part(request.part_id)
        if part is None:
            raise ValueError(f"unknown part_id: {request.part_id}")
        merged: dict[str, Any] = {parameter.name: parameter for parameter in part.parameters}
        for value in values:
            name = getattr(value, "name", None)
            if not name:
                continue
            value.part_id = part.part_id
            if not value.param_id:
                value.param_id = f"{part.part_id}:{name}"
            merged[name] = value
        part.parameters = list(merged.values())
        if request.family is not None:
            part.family = request.family
        if result.source_id and result.source_id not in part.source_ids:
            part.source_ids.append(result.source_id)
        stored = self._repository.add_part(part)
        return stored
