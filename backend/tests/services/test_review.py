"""Review service tests (FR-10)."""

from __future__ import annotations

from services.review import ReviewService
from shared.schemas import ReviewDecision, ValueStatus
from tests.services.fakes import FakePartsRepository, make_part


def _repository() -> FakePartsRepository:
    part = make_part(
        "p-review",
        "REV-1",
        parameters={"vds_max": 100.0, "rds_on": 12.0},
    )
    part.parameters[0].status = ValueStatus.REVIEW
    part.parameters[0].confidence = 0.4
    part.parameters[0].param_id = "p-review:vds_max"
    part.parameters[1].status = ValueStatus.REVIEW
    part.parameters[1].confidence = 0.5
    part.parameters[1].param_id = "p-review:rds_on"
    return FakePartsRepository([part])


def test_the_queue_is_returned_by_the_repository() -> None:
    repo = _repository()
    service = ReviewService(repo)

    items = service.queue()

    assert len(items) == 2
    assert {item.name for item in items} == {"vds_max", "rds_on"}
    assert repo.calls_to("list_review_queue")


def test_the_queue_can_be_paginated() -> None:
    service = ReviewService(_repository())

    items = service.queue(limit=1, offset=1)

    assert len(items) == 1


def test_accepting_a_value() -> None:
    repo = _repository()
    service = ReviewService(repo)

    response = service.decide("p-review:vds_max", ReviewDecision(action="accept"))

    assert response.param_id == "p-review:vds_max"
    assert response.status == ValueStatus.ACCEPTED
    assert response.message
    stored = repo.get_parameter("p-review:vds_max")
    assert stored is not None
    assert stored.status == ValueStatus.ACCEPTED


def test_correcting_a_value() -> None:
    repo = _repository()
    service = ReviewService(repo)

    response = service.decide(
        "p-review:rds_on",
        ReviewDecision(action="correct", value=11.5, unit="mohm", note="from the datasheet"),
    )

    assert response.status == ValueStatus.ACCEPTED
    stored = repo.get_parameter("p-review:rds_on")
    assert stored is not None
    assert stored.value == 11.5
    assert stored.unit == "mohm"


def test_rejecting_a_value() -> None:
    repo = _repository()
    service = ReviewService(repo)

    response = service.decide("p-review:vds_max", ReviewDecision(action="reject"))

    assert response.status == ValueStatus.REJECTED
    stored = repo.get_parameter("p-review:vds_max")
    assert stored is not None
    assert stored.status == ValueStatus.REJECTED


def test_an_unknown_parameter_is_reported() -> None:
    service = ReviewService(_repository())

    response = service.decide("does-not-exist", ReviewDecision(action="accept"))

    assert response.param_id == "does-not-exist"
    assert response.message == "unknown parameter"


def test_the_reviewed_value_leaves_the_queue() -> None:
    service = ReviewService(_repository())

    service.decide("p-review:vds_max", ReviewDecision(action="accept"))

    assert len(service.queue()) == 1
