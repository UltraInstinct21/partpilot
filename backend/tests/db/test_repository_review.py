"""The review queue and the human decisions (FR-10)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db.models import ReviewCorrectionRow
from shared.schemas import ExtractionMethod, ReviewDecision, ValueStatus
from tests.db.conftest import make_part, make_value


def _seed(repo) -> None:
    repo.add_part(
        make_part(
            part_id="p1",
            mpn="IRF3205S",
            parameters=[
                make_value("vds_max", 56.0, "V", confidence=0.9, status=ValueStatus.ACCEPTED),
                make_value(
                    "rds_on",
                    0.012,
                    "ohm",
                    confidence=0.42,
                    status=ValueStatus.REVIEW,
                    condition={"Vgs": "10 V"},
                    raw_text="RDS(on) 12 mOhm",
                ),
                make_value(
                    "vgs_max",
                    20.0,
                    "V",
                    confidence=0.61,
                    status=ValueStatus.REVIEW,
                ),
                make_value("vgs_threshold", 2.47, "V", status=ValueStatus.REJECTED),
            ],
        )
    )


def test_review_queue_only_contains_review_values(repo) -> None:
    _seed(repo)
    queue = repo.list_review_queue()
    assert [item.name for item in queue] == ["rds_on", "vgs_max"]
    assert {item.status for item in queue} == {ValueStatus.REVIEW}
    assert queue[0].mpn == "IRF3205S"
    assert queue[0].manufacturer == "International Rectifier"
    assert queue[0].confidence == 0.42
    assert queue[0].condition == {"Vgs": "10 V"}


def test_review_queue_is_sorted_by_confidence_ascending(repo) -> None:
    _seed(repo)
    queue = repo.list_review_queue()
    confidences = [item.confidence for item in queue]
    assert confidences == sorted(confidences)


def test_review_queue_supports_limit_and_offset(repo) -> None:
    _seed(repo)
    assert len(repo.list_review_queue(limit=1)) == 1
    assert len(repo.list_review_queue(limit=1, offset=1)) == 1
    assert repo.list_review_queue(limit=1, offset=1)[0].name == "vgs_max"


def test_apply_review_accept(repo) -> None:
    _seed(repo)
    param_id = repo.list_review_queue()[0].param_id
    response = repo.apply_review(param_id, ReviewDecision(action="accept"))
    assert response.param_id == param_id
    assert response.status is ValueStatus.ACCEPTED
    assert response.item is not None
    assert response.item.status is ValueStatus.ACCEPTED
    assert response.item.confidence == 1.0
    assert response.item.method is ExtractionMethod.MANUAL

    value = repo.get_parameter(param_id)
    assert value.status is ValueStatus.ACCEPTED
    assert value.method is ExtractionMethod.MANUAL
    assert value.confidence == 1.0


def test_apply_review_correct(repo) -> None:
    _seed(repo)
    param_id = repo.list_review_queue()[0].param_id
    response = repo.apply_review(
        param_id,
        ReviewDecision(
            action="correct",
            value=0.011,
            value_min=0.010,
            value_typ=0.011,
            value_max=0.013,
            unit="ohm",
            condition={"Vgs": "10 V", "Tj": "25 C"},
            note="the table says 11 mOhm",
        ),
    )
    assert response.status is ValueStatus.ACCEPTED
    assert response.item is not None
    assert response.item.method is ExtractionMethod.MANUAL
    assert response.item.confidence == 1.0

    value = repo.get_parameter(param_id)
    assert value.value == 0.011
    assert value.value_min == 0.010
    assert value.value_typ == 0.011
    assert value.value_max == 0.013
    assert value.unit == "ohm"
    assert value.condition == {"Vgs": "10 V", "Tj": "25 C"}
    assert value.status is ValueStatus.ACCEPTED


def test_apply_review_reject(repo) -> None:
    _seed(repo)
    param_id = repo.list_review_queue()[0].param_id
    response = repo.apply_review(param_id, ReviewDecision(action="reject"))
    assert response.status is ValueStatus.REJECTED
    assert response.item is not None
    assert response.item.status is ValueStatus.REJECTED

    value = repo.get_parameter(param_id)
    assert value.status is ValueStatus.REJECTED


def test_apply_review_writes_a_correction_row(repo, engine) -> None:
    _seed(repo)
    param_id = repo.list_review_queue()[0].param_id
    repo.apply_review(
        param_id,
        ReviewDecision(action="correct", value=0.011, note="checked by hand"),
    )
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                ReviewCorrectionRow.correction_id,
                ReviewCorrectionRow.param_id,
                ReviewCorrectionRow.part_id,
                ReviewCorrectionRow.action,
                ReviewCorrectionRow.old_value,
                ReviewCorrectionRow.new_value,
                ReviewCorrectionRow.note,
            )
        ).all()
    assert len(rows) == 1
    correction_id, stored_param_id, part_id, action, old_value, new_value, note = rows[0]
    assert correction_id
    assert stored_param_id == param_id
    assert part_id == "p1"
    assert action == "correct"
    assert old_value == 0.012
    assert new_value == 0.011
    assert note == "checked by hand"


def test_apply_review_of_an_unknown_param_raises(repo) -> None:
    with pytest.raises(KeyError):
        repo.apply_review("nope", ReviewDecision(action="accept"))


def test_review_queue_is_empty_after_the_decisions(repo) -> None:
    _seed(repo)
    for item in repo.list_review_queue():
        repo.apply_review(item.param_id, ReviewDecision(action="accept"))
    assert repo.list_review_queue() == []
