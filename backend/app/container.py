"""The application container.

The container is the single object that holds every collaborator of the API.
It is created by :func:`app.wiring.build_container` and stored on
``app.state.container`` so that the FastAPI dependency injection can hand it
to the routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rate_limit import FixedWindowRateLimiter
from shared.config import Settings
from shared.interfaces import (
    AlternativesService,
    BomService,
    JobRunner,
    LLMExtractor,
    PartsRepository,
    ReviewService,
    SearchService,
    StatsService,
    Tier1Extractor,
    Validator,
)


@dataclass
class Container:
    """Every collaborator the API needs.

    The types are the protocols of ``shared.interfaces``: the real
    implementations of the other agents satisfy them without inheritance.
    """

    settings: Settings
    repository: PartsRepository
    search_service: SearchService
    alternatives_service: AlternativesService
    bom_service: BomService
    review_service: ReviewService
    stats_service: StatsService
    llm_extractor: LLMExtractor
    tier1_extractor: Tier1Extractor
    validator: Validator
    job_runner: JobRunner
    rate_limiter: FixedWindowRateLimiter = field(default_factory=FixedWindowRateLimiter)


__all__ = ["Container"]
