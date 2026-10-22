"""FastAPI dependency providers.

Every collaborator is taken from the container on ``app.state.container``,
which is built by :func:`app.wiring.build_container`. A test can replace any
of them with ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.container import Container
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


def get_container(request: Request) -> Container:
    """The container of the running application."""
    return request.app.state.container


def get_settings_dep(container: Container = Depends(get_container)) -> Settings:
    """The runtime settings."""
    return container.settings


def get_repository(container: Container = Depends(get_container)) -> PartsRepository:
    """The parts repository."""
    return container.repository


def get_search_service(container: Container = Depends(get_container)) -> SearchService:
    """The search service."""
    return container.search_service


def get_alternatives_service(container: Container = Depends(get_container)) -> AlternativesService:
    """The alternatives service."""
    return container.alternatives_service


def get_bom_service(container: Container = Depends(get_container)) -> BomService:
    """The BOM service."""
    return container.bom_service


def get_review_service(container: Container = Depends(get_container)) -> ReviewService:
    """The review service."""
    return container.review_service


def get_stats_service(container: Container = Depends(get_container)) -> StatsService:
    """The stats service."""
    return container.stats_service


def get_llm_extractor(container: Container = Depends(get_container)) -> LLMExtractor:
    """The LLM extractor (tiers 2 and 3)."""
    return container.llm_extractor


def get_tier1_extractor(container: Container = Depends(get_container)) -> Tier1Extractor:
    """The tier 1 (rule based) extractor."""
    return container.tier1_extractor


def get_validator(container: Container = Depends(get_container)) -> Validator:
    """The validator."""
    return container.validator


def get_job_runner(container: Container = Depends(get_container)) -> JobRunner:
    """The background job runner."""
    return container.job_runner


def get_rate_limiter(container: Container = Depends(get_container)) -> FixedWindowRateLimiter:
    """The rate limiter of ``POST /api/search``."""
    return container.rate_limiter


__all__ = [
    "get_alternatives_service",
    "get_bom_service",
    "get_container",
    "get_job_runner",
    "get_llm_extractor",
    "get_rate_limiter",
    "get_repository",
    "get_review_service",
    "get_search_service",
    "get_settings_dep",
    "get_stats_service",
    "get_tier1_extractor",
    "get_validator",
]
