"""PartPilot services (plan WP6).

Every service takes its collaborators by **injection**, so the API layer can
wire the real implementations or a test double without any import from another
agent's package.

The public classes satisfy the protocols of :mod:`shared.interfaces`:

* :class:`~services.search.SearchService` -> ``SearchService``
* :class:`~services.alternatives.AlternativesService` -> ``AlternativesService``
* :class:`~services.bom.BomService` -> ``BomService``
* :class:`~services.review.ReviewService` -> ``ReviewService``
* :class:`~services.stats.StatsService` -> ``StatsService``
* :class:`~services.jobs.BackgroundJobRunner` -> ``JobRunner``
"""

from __future__ import annotations

from services.alternatives import AlternativesService
from services.bom import BomService
from services.jobs import BackgroundJobRunner
from services.review import ReviewService
from services.search import SearchService, describe_filter
from services.stats import StatsService

__all__ = [
    "AlternativesService",
    "BackgroundJobRunner",
    "BomService",
    "ReviewService",
    "SearchService",
    "StatsService",
    "describe_filter",
]
