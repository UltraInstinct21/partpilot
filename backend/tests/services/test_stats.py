"""Stats service tests (plan WP7/WP8)."""

from __future__ import annotations

from services.stats import StatsService
from tests.services.fakes import FakePartsRepository


def test_the_numbers_come_from_the_repository() -> None:
    repo = FakePartsRepository()
    service = StatsService(repo)

    stats = service.stats()
    direct = repo.stats()

    assert stats.parts_total == direct.parts_total
    assert stats.parameters_total == direct.parameters_total
    assert stats.parts_by_family == direct.parts_by_family
    assert stats.values_by_status == direct.values_by_status
    assert stats.parts_total == 30
    assert stats.parts_by_family["mosfet"] == 15
    assert stats.parts_by_family["gate_driver"] == 15
    assert stats.parts_by_lifecycle["active"] == 29
    assert stats.parts_by_lifecycle["nrnd"] == 1
    assert stats.parameters_total == 30 * 13
    assert stats.review_pending == 0
    assert stats.coverage_pct == 100.0
    assert 0.0 < stats.mean_confidence <= 1.0
    assert repo.calls_to("stats")


def test_an_empty_repository_returns_zeros() -> None:
    service = StatsService(FakePartsRepository(seed=False))

    stats = service.stats()

    assert stats.parts_total == 0
    assert stats.parameters_total == 0
    assert stats.coverage_pct == 0.0
    assert stats.mean_confidence == 0.0


def test_the_review_queue_is_counted() -> None:
    repo = FakePartsRepository(seed=False)
    service = StatsService(repo)

    stats = service.stats()

    assert stats.review_pending == 0
    assert stats.parts_total == 0
