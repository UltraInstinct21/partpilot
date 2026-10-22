"""Background job tests (plan WP6)."""

from __future__ import annotations

import time

import pytest

from services.jobs import BackgroundJobRunner
from shared.schemas import (
    ExtractionMethod,
    ExtractionResult,
    Family,
    JobRequest,
    JobState,
    ParameterValue,
)
from tests.services.fakes import (
    FakeLLMExtractor,
    FakePartsRepository,
    FakeTier1Extractor,
    FakeValidator,
)

PDF_PATH = "/tmp/partpilot-test.pdf"


def _tier1_result() -> ExtractionResult:
    return ExtractionResult(
        family=Family.MOSFET,
        method=ExtractionMethod.TIER1,
        source_id="src-1",
        values=[
            ParameterValue(
                name="vds_max",
                value=100.0,
                unit="V",
                method=ExtractionMethod.TIER1,
                confidence=0.85,
            )
        ],
        pages_used=[1],
    )


def _wait(runner: BackgroundJobRunner, job_id: str, timeout: float = 5.0) -> object:
    deadline = time.monotonic() + timeout
    status = runner.get(job_id)
    while status is not None and status.state in (JobState.QUEUED, JobState.RUNNING):
        if time.monotonic() > deadline:
            raise AssertionError(f"the job did not finish: {status.state}")
        time.sleep(0.01)
        status = runner.get(job_id)
    assert status is not None
    return status


def test_submit_returns_queued_immediately() -> None:
    runner = BackgroundJobRunner(FakePartsRepository(), FakeTier1Extractor(_tier1_result()))

    started = time.monotonic()
    status = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))
    elapsed = time.monotonic() - started

    assert status.state == JobState.QUEUED
    assert status.job_id
    assert elapsed < 1.0


def test_the_job_reaches_completed() -> None:
    repo = FakePartsRepository()
    validator = FakeValidator()
    runner = BackgroundJobRunner(repo, FakeTier1Extractor(_tier1_result()), validator=validator)

    status = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))
    final = _wait(runner, status.job_id)

    assert final.state == JobState.COMPLETED
    assert final.progress == 100
    assert final.error is None
    assert final.result is not None
    assert final.result["values"] == 1
    assert validator.calls


def test_the_extracted_value_is_validated_and_stored() -> None:
    repo = FakePartsRepository()
    validator = FakeValidator(bump=0.1)
    runner = BackgroundJobRunner(repo, FakeTier1Extractor(_tier1_result()), validator=validator)

    status = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))
    _wait(runner, status.job_id)

    part = repo.get_part("mosfet-irf3205s")
    assert part is not None
    stored = {parameter.name: parameter for parameter in part.parameters}["vds_max"]
    assert stored.value == 100.0
    assert stored.confidence == pytest.approx(0.95)


def test_a_failing_extraction_reaches_failed() -> None:
    tier1 = FakeTier1Extractor(error=RuntimeError("the PDF is broken"))
    runner = BackgroundJobRunner(FakePartsRepository(), tier1)

    status = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))
    final = _wait(runner, status.job_id)

    assert final.state == JobState.FAILED
    assert final.error
    assert "broken" in final.error


def test_a_missing_pdf_path_fails_the_job() -> None:
    runner = BackgroundJobRunner(FakePartsRepository(), FakeTier1Extractor(_tier1_result()))

    status = runner.submit(JobRequest(part_id="mosfet-irf3205s"))
    final = _wait(runner, status.job_id)

    assert final.state == JobState.FAILED
    assert "pdf_path" in (final.error or "")


def test_an_unknown_part_id_fails_the_job() -> None:
    runner = BackgroundJobRunner(FakePartsRepository(), FakeTier1Extractor(_tier1_result()))

    status = runner.submit(JobRequest(part_id="not-a-part", pdf_path=PDF_PATH))
    final = _wait(runner, status.job_id)

    assert final.state == JobState.FAILED
    assert "unknown part_id" in (final.error or "")


def test_tier_two_is_used_when_tier_one_fails() -> None:
    empty = ExtractionResult(family=Family.MOSFET, method=ExtractionMethod.TIER1, values=[])
    tier2 = ExtractionResult(
        family=Family.MOSFET,
        method=ExtractionMethod.TIER2,
        values=[
            ParameterValue(
                name="vds_max",
                value=100.0,
                unit="V",
                method=ExtractionMethod.TIER2,
                confidence=0.75,
            )
        ],
    )
    llm = FakeLLMExtractor(tier2_result=tier2)
    runner = BackgroundJobRunner(FakePartsRepository(), FakeTier1Extractor(empty), llm)

    status = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))
    final = _wait(runner, status.job_id)

    assert llm.call_counts["extract_tier2"] == 1
    assert final.state == JobState.COMPLETED
    assert final.result is not None
    assert final.result["method"] == ExtractionMethod.TIER2.value


def test_get_returns_none_for_an_unknown_job() -> None:
    runner = BackgroundJobRunner(FakePartsRepository(), FakeTier1Extractor(_tier1_result()))

    assert runner.get("does-not-exist") is None


def test_the_job_list_is_newest_first() -> None:
    runner = BackgroundJobRunner(FakePartsRepository(), FakeTier1Extractor(_tier1_result()))

    first = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))
    second = runner.submit(JobRequest(part_id="mosfet-irf540n", pdf_path=PDF_PATH))
    jobs = runner.list()

    assert len(jobs) == 2
    assert jobs[0].job_id == second.job_id
    assert jobs[1].job_id == first.job_id
    assert runner.list(limit=1) == [jobs[0]]


def test_a_background_task_object_is_used_when_it_is_given() -> None:
    class FakeBackgroundTasks:
        def __init__(self) -> None:
            self.tasks: list[tuple] = []

        def add_task(self, func, *args, **kwargs) -> None:
            self.tasks.append((func, args, kwargs))

    tasks = FakeBackgroundTasks()
    runner = BackgroundJobRunner(
        FakePartsRepository(), FakeTier1Extractor(_tier1_result()), background_tasks=tasks
    )

    status = runner.submit(JobRequest(part_id="mosfet-irf3205s", pdf_path=PDF_PATH))

    assert len(tasks.tasks) == 1
    assert runner.get(status.job_id).state == JobState.QUEUED
    # The task is executed by FastAPI after the response was sent.
    func, args, _kwargs = tasks.tasks[0]
    func(*args)
    assert runner.get(status.job_id).state == JobState.COMPLETED
