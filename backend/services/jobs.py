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

import logging
import threading
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from shared.config import Settings, get_settings, resolve_pdf_path
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

logger = logging.getLogger(__name__)

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
        settings: Settings | None = None,
        background_tasks: Any | None = None,
        pages_provider: PagesProvider | None = None,
        max_jobs: int = 200,
    ) -> None:
        self.settings = settings or get_settings()
        self._repository = repository
        self._tier1 = tier1
        self._llm = llm
        self._validator = validator
        self._background_tasks = background_tasks
        self._pages_provider = pages_provider
        self._max_jobs = max(1, int(max_jobs))
        self._jobs: dict[str, JobStatus] = {}
        self._requests: dict[str, JobRequest] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    # -- registry ---------------------------------------------------------------

    def _remember(self, status: JobStatus, request: JobRequest | None = None) -> None:
        with self._lock:
            self._jobs[status.job_id] = status
            if request is not None:
                self._requests[status.job_id] = request
            self._order.append(status.job_id)
            while len(self._order) > self._max_jobs:
                old = self._order.pop(0)
                self._jobs.pop(old, None)
                self._requests.pop(old, None)

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
        self._remember(status, request)
        # Take the snapshot before the work starts: the worker may already
        # have changed the state when the copy is made.
        snapshot = status.model_copy(deep=True)
        self._schedule(job_id, request)
        return snapshot

    def run(self, job_id: str) -> JobStatus | None:
        """Execute a queued job (called from FastAPI background tasks or runner)."""
        with self._lock:
            status = self._jobs.get(job_id)
            if status is None or status.state != JobState.QUEUED:
                return status
            request = self._requests.get(job_id)
        if request is not None:
            return self.run_job(job_id, request)
        return status

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
        with self._lock:
            status = self._jobs.get(job_id)
            if status is not None and status.state in {JobState.RUNNING, JobState.COMPLETED}:
                return status
        try:
            self._update(job_id, state=JobState.RUNNING, progress=10, message="locating and preparing datasheet PDF")
            resolved_request = self._prepare_request(request)
            self._update(job_id, progress=30, message="extracting parameters from PDF")
            result = self._extract(resolved_request)
            self._update(job_id, progress=60, message="validating the values")
            values = self._validate(result)
            self._update(job_id, progress=80, message="storing the values")
            stored = self._store(resolved_request, result, values)
            payload: dict[str, Any] = {
                "part_id": stored.part_id if stored else resolved_request.part_id,
                "values": len(values),
                "failed_fields": list(result.failed_fields),
                "pages_used": list(result.pages_used),
                "method": result.method.value if result.method else None,
                "source_id": result.source_id or resolved_request.source_id,
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
            logger.exception("Job %s failed: %s", job_id, exc)
            status = self._update(
                job_id,
                state=JobState.FAILED,
                message=f"failed: {exc}",
                error=str(exc),
            )
        return status if status is not None else JobStatus(job_id=job_id, state=JobState.FAILED)

    def _prepare_request(self, request: JobRequest) -> JobRequest:
        """Resolve pdf_path, part_id, family, and source_id robustly."""
        req = request.model_copy()
        part = None
        if req.part_id:
            try:
                part = self._repository.get_part(req.part_id)
            except Exception:
                part = None
            if part:
                if req.family is None and part.family:
                    req.family = part.family

        # 1. If pdf_path is provided, resolve it if possible but keep it
        if req.pdf_path:
            resolved = resolve_pdf_path(req.pdf_path, self.settings)
            if resolved and resolved.is_file():
                req.pdf_path = str(resolved)

        # 2. Check part.source_ids for existing cached PDF
        if not req.pdf_path and part:
            for s_id in part.source_ids:
                try:
                    source = self._repository.get_source(s_id)
                except Exception:
                    source = None
                if source and source.type.value == "pdf" and source.local_path:
                    resolved = resolve_pdf_path(source.local_path, self.settings)
                    if resolved and resolved.is_file():
                        req.pdf_path = str(resolved)
                        if not req.source_id:
                            req.source_id = source.source_id
                        break

        # 3. If source_id is provided and no pdf_path
        if not req.pdf_path and req.source_id:
            try:
                source = self._repository.get_source(req.source_id)
            except Exception:
                source = None
            if source and source.local_path:
                resolved = resolve_pdf_path(source.local_path, self.settings)
                if resolved and resolved.is_file():
                    req.pdf_path = str(resolved)

        # 4. If still no pdf_path and part is known, auto-resolve & download on real repositories
        if not req.pdf_path and part and not type(self._repository).__name__.startswith("Fake"):
            try:
                from collectors.datasheets import DatasheetResolver

                resolver = DatasheetResolver(self.settings)
                source = resolver.resolve_and_download(
                    mpn=part.mpn,
                    manufacturer=part.manufacturer,
                    direct_url=part.datasheet_url,
                    part_id=part.part_id,
                )
                if source and source.local_path:
                    resolved = resolve_pdf_path(source.local_path, self.settings)
                    if resolved and resolved.is_file():
                        req.pdf_path = str(resolved)
                        if not req.source_id:
                            req.source_id = source.source_id
                        try:
                            self._repository.add_source(source)
                            if source.source_id not in part.source_ids:
                                self._repository.add_part(
                                    part.model_copy(update={"source_ids": [*part.source_ids, source.source_id]})
                                )
                        except Exception:
                            pass
            except Exception as exc:
                logger.warning("Failed to auto-resolve datasheet for part %s: %s", req.part_id, exc)

        # 5. If still no pdf_path, fail with ValueError("pdf_path is required")
        if not req.pdf_path:
            raise ValueError("pdf_path is required")

        return req

    # -- the pipeline -----------------------------------------------------------

    def _extract(self, request: JobRequest) -> ExtractionResult:
        """Run extraction across Tier 1 (rules), Tier 2 (LLM text), or Tier 3 (LLM vision)."""
        if not request.pdf_path:
            raise ValueError("pdf_path is required")
        family = request.family or Family.MOSFET
        part_id = request.part_id
        source_id = request.source_id

        # 1. Force Tier 3 (Vision)
        if request.force_tier == 3:
            if self._llm is None:
                raise RuntimeError("Tier 3 requested but LLM extractor is not configured")
            images = self._page_images(request.pdf_path)
            return self._llm.extract_tier3(images, family, part_id)

        # 2. Force Tier 2 (LLM Text)
        if request.force_tier == 2:
            if self._llm is None:
                raise RuntimeError("Tier 2 requested but LLM extractor is not configured")
            pages = self._pages(request.pdf_path)
            return self._llm.extract_tier2(pages, family, part_id)

        # 3. Default: Run Tier 1 first
        result: ExtractionResult | None = None
        tier1_error: Exception | None = None
        if self._tier1 is not None:
            try:
                result = self._tier1.extract(request.pdf_path, family)
                if result is not None and not result.source_id and source_id:
                    result = result.model_copy(update={"source_id": source_id})
            except Exception as exc:  # noqa: BLE001 - tier 1 may fail on complex PDFs
                logger.warning("Tier 1 extraction failed: %s", exc)
                tier1_error = exc
                result = None

        # Check for scanned PDF
        if result is not None and getattr(result, "scanned", False):
            if self._llm is not None:
                images = self._page_images(request.pdf_path)
                if images:
                    try:
                        return self._llm.extract_tier3(images, family, part_id)
                    except Exception as exc:
                        logger.warning("Tier 3 fallback failed for scanned document: %s", exc)
            return result

        # If tier 1 yielded no values, try Tier 2 LLM
        if result is None or not result.values:
            if self._llm is not None:
                pages = self._pages(request.pdf_path)
                try:
                    result = self._llm.extract_tier2(pages, family, part_id)
                except Exception as exc:
                    logger.warning("Tier 2 extraction failed: %s", exc)
            if result is None or not result.values:
                if tier1_error is not None:
                    raise RuntimeError(f"tier 1 extraction failed: {tier1_error}") from tier1_error
                raise RuntimeError("tier 1 returned no values")
        elif self._llm is not None and len(result.failed_fields) > 0:
            # Tier 1 extracted partial values. Use Tier 2 to supplement failed fields
            pages = self._pages(request.pdf_path)
            if pages:
                try:
                    tier2_res = self._llm.extract_tier2(pages, family, part_id)
                    if tier2_res and tier2_res.values:
                        existing = {v.name for v in result.values}
                        merged_vals = list(result.values)
                        for v in tier2_res.values:
                            if v.name not in existing:
                                v.part_id = part_id
                                v.source_id = source_id or result.source_id
                                merged_vals.append(v)
                                existing.add(v.name)
                        result = result.model_copy(
                            update={
                                "values": merged_vals,
                                "failed_fields": [f for f in result.failed_fields if f not in existing],
                                "pages_used": sorted(set(result.pages_used + tier2_res.pages_used)),
                            }
                        )
                except Exception as exc:
                    logger.warning("Tier 2 supplement failed: %s", exc)

        return result

    def _page_images(self, pdf_path: str, max_pages: int = 3) -> list[tuple[int, bytes]]:
        """Render page images for tier 3 vision extraction."""
        from app.pdf import render_page_png

        images: list[tuple[int, bytes]] = []
        for page_num in range(1, max_pages + 1):
            png = render_page_png(pdf_path, page_num)
            if png:
                images.append((page_num, png))
        return images

    def _pages(self, pdf_path: str, max_pages: int = 5) -> list[tuple[int, str]]:
        """Return the page text used by the tier 2 fallback."""
        if self._pages_provider is not None:
            return list(self._pages_provider(pdf_path))
        from extraction.tier1.page_finder import find_pages

        try:
            target_pages = find_pages(pdf_path)[:max_pages]
        except Exception:
            target_pages = []
        if not target_pages:
            target_pages = list(range(1, max_pages + 1))

        pages: list[tuple[int, str]] = []
        try:
            import pymupdf

            with pymupdf.open(pdf_path) as doc:
                for p_num in target_pages:
                    if 1 <= p_num <= doc.page_count:
                        text = doc[p_num - 1].get_text() or ""
                        if text.strip():
                            pages.append((p_num, text))
        except Exception:
            try:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    for p_num in target_pages:
                        if 1 <= p_num <= len(pdf.pages):
                            text = pdf.pages[p_num - 1].extract_text() or ""
                            if text.strip():
                                pages.append((p_num, text))
            except Exception:
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
        source_id = request.source_id or result.source_id

        part_id = request.part_id
        if not part_id:
            guessed_mpn = result.part_number or (Path(request.pdf_path).stem if request.pdf_path else "unknown")
            fam = request.family or Family.GENERAL
            part_id = f"{fam.value}-{guessed_mpn.lower().replace('_', '-').strip('-')}"

        part = self._repository.get_part(part_id)
        if part is None:
            guessed_mpn = result.part_number or (Path(request.pdf_path).stem if request.pdf_path else part_id)
            fam = request.family or Family.GENERAL
            part = PartRecord(
                part_id=part_id,
                mpn=guessed_mpn,
                manufacturer="Datasheet Extraction",
                family=fam,
                parameters=[],
                source_ids=[source_id] if source_id else [],
            )

        merged: dict[str, Any] = {parameter.name: parameter for parameter in part.parameters}
        for value in values:
            name = getattr(value, "name", None)
            if not name:
                continue
            value.part_id = part.part_id
            if not value.param_id:
                value.param_id = f"{part.part_id}:{name}"
            if not getattr(value, "source_id", None) and source_id:
                value.source_id = source_id
            merged[name] = value
        part.parameters = list(merged.values())
        if request.family is not None:
            part.family = request.family
        if source_id and source_id not in part.source_ids:
            part.source_ids.append(source_id)
        stored = self._repository.add_part(part)

        # Cache extracted page texts if source_id is known
        if source_id and request.pdf_path:
            try:
                pages = self._pages(request.pdf_path)
                for p_num, text in pages:
                    self._repository.add_source_page(source_id, p_num, text=text)
            except Exception as page_exc:
                logger.warning("Could not cache source pages in repository: %s", page_exc)

        return stored
