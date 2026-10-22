"""The services must satisfy the frozen protocols of ``shared.interfaces``."""

from __future__ import annotations

from services.alternatives import AlternativesService
from services.bom import BomService
from services.jobs import BackgroundJobRunner
from services.review import ReviewService
from services.search import SearchService
from services.stats import StatsService
from shared import interfaces
from tests.services.fakes import FakePartsRepository


def test_the_services_satisfy_the_frozen_protocols() -> None:
    repo = FakePartsRepository()
    assert isinstance(SearchService(repo), interfaces.SearchService)
    assert isinstance(AlternativesService(repo), interfaces.AlternativesService)
    assert isinstance(BomService(repo), interfaces.BomService)
    assert isinstance(ReviewService(repo), interfaces.ReviewService)
    assert isinstance(StatsService(repo), interfaces.StatsService)
    assert isinstance(BackgroundJobRunner(repo), interfaces.JobRunner)
