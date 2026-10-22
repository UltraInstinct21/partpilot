"""Background extraction jobs (``/api/jobs``)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path

from app.dependencies import get_job_runner
from shared.interfaces import JobRunner
from shared.schemas import JobRequest, JobStatus

router = APIRouter(prefix="/api", tags=["jobs"])


def _run_job(runner: Any, job_id: str) -> None:
    """Execute a queued job (called from the background task)."""
    run = getattr(runner, "run", None)
    if callable(run):
        run(job_id)


@router.post(
    "/jobs/extract",
    response_model=JobStatus,
    status_code=202,
    operation_id="startExtractionJob",
    summary="Start a background extraction job",
    responses={
        202: {"description": "The job was accepted."},
        422: {"description": "The request body did not validate."},
    },
)
def start_extraction_job(
    background_tasks: BackgroundTasks,
    payload: JobRequest | None = Body(default=None),
    runner: JobRunner = Depends(get_job_runner),
) -> JobStatus:
    """Queue an extraction job and return its initial status."""
    request = payload or JobRequest()
    job = runner.submit(request)
    background_tasks.add_task(_run_job, runner, job.job_id)
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    operation_id="getJob",
    summary="Get the progress of a background job",
    responses={404: {"description": "The job does not exist."}},
)
def get_job(
    job_id: str = Path(description="The identifier of the job."),
    runner: JobRunner = Depends(get_job_runner),
) -> JobStatus:
    """Return the current status of a background job."""
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")
    return job


__all__ = ["router"]
