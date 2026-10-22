"""The composition root of the API.

**This is the one file that changes when the real implementations arrive.**

Right now every collaborator is a fake from :mod:`app.fakes`, so the API runs
standalone. In the integration phase the orchestrator replaces the entries of
:data:`FACTORIES` with the real factories of the other agents. The routes do
not change, because they only use the protocols of ``shared.interfaces``.

Expected constructor signatures (derived from ``shared/interfaces.py``)::

    repository       PartsRepository(settings)               # agent E
    llm_extractor    LLMExtractor(settings)                  # agent C
    tier1_extractor  Tier1Extractor(settings)                # agent B
    validator        Validator(settings)                     # agent D
    search_service   SearchService(repository, llm_extractor)          # agent F
    alternatives     AlternativesService(repository, llm_extractor)    # agent F
    bom_service      BomService(repository)                  # agent F
    review_service   ReviewService(repository)               # agent F
    stats_service    StatsService(repository)                # agent F
    job_runner       JobRunner(repository, tier1_extractor, validator)  # agent F

A factory may accept any subset of the keyword arguments
``settings``, ``repository``, ``llm_extractor``, ``tier1_extractor`` and
``validator``; only the ones it declares are passed.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from app.container import Container
from app.fakes.llm import StubLLMExtractor
from app.fakes.repository import InMemoryPartsRepository
from app.fakes.services import (
    FakeAlternativesService,
    FakeBomService,
    FakeJobRunner,
    FakeReviewService,
    FakeSearchService,
    FakeStatsService,
)
from app.fakes.tier1 import StubTier1Extractor
from app.fakes.validator import StubValidator
from app.rate_limit import FixedWindowRateLimiter
from shared.config import Settings, get_settings

Factory = Callable[..., Any]


def _default_repository(settings: Settings, **_: Any) -> InMemoryPartsRepository:
    """The fake repository (agent E replaces it)."""
    return InMemoryPartsRepository(settings)


def _default_llm(settings: Settings, **_: Any) -> StubLLMExtractor:
    """The fake LLM extractor (agent C replaces it)."""
    return StubLLMExtractor()


def _default_tier1(settings: Settings, **_: Any) -> StubTier1Extractor:
    """The fake tier 1 extractor (agent B replaces it)."""
    return StubTier1Extractor()


def _default_validator(settings: Settings, **_: Any) -> StubValidator:
    """The fake validator (agent D replaces it)."""
    return StubValidator()


def _default_search_service(repository: Any, llm_extractor: Any, **_: Any) -> FakeSearchService:
    """The fake search service (agent F replaces it)."""
    return FakeSearchService(repository, llm_extractor)


def _default_alternatives_service(
    repository: Any, llm_extractor: Any, **_: Any
) -> FakeAlternativesService:
    """The fake alternatives service (agent F replaces it)."""
    return FakeAlternativesService(repository, llm_extractor)


def _default_bom_service(repository: Any, **_: Any) -> FakeBomService:
    """The fake BOM service (agent F replaces it)."""
    return FakeBomService(repository)


def _default_review_service(repository: Any, **_: Any) -> FakeReviewService:
    """The fake review service (agent F replaces it)."""
    return FakeReviewService(repository)


def _default_stats_service(repository: Any, **_: Any) -> FakeStatsService:
    """The fake stats service (agent F replaces it)."""
    return FakeStatsService(repository)


def _default_job_runner(repository: Any, tier1_extractor: Any, **_: Any) -> FakeJobRunner:
    """The fake job runner (agent F replaces it)."""
    return FakeJobRunner(repository, tier1_extractor)


#: The factories of the composition root. The integration phase swaps the
#: entries here - and only here - for the real implementations.
FACTORIES: dict[str, Factory] = {
    "repository": _default_repository,
    "llm_extractor": _default_llm,
    "tier1_extractor": _default_tier1,
    "validator": _default_validator,
    "search_service": _default_search_service,
    "alternatives_service": _default_alternatives_service,
    "bom_service": _default_bom_service,
    "review_service": _default_review_service,
    "stats_service": _default_stats_service,
    "job_runner": _default_job_runner,
}


def _call(factory: Factory, **kwargs: Any) -> Any:
    """Call a factory with the keyword arguments it accepts."""
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):  # pragma: no cover - builtins without signature
        return factory(**kwargs)
    parameters = signature.parameters
    if any(item.kind is item.VAR_KEYWORD for item in parameters.values()):
        return factory(**kwargs)
    accepted = {name: value for name, value in kwargs.items() if name in parameters}
    return factory(**accepted)


def build_container(
    settings: Settings | None = None,
    *,
    repository: Any | None = None,
    llm_extractor: Any | None = None,
    tier1_extractor: Any | None = None,
    validator: Any | None = None,
    search_service: Any | None = None,
    alternatives_service: Any | None = None,
    bom_service: Any | None = None,
    review_service: Any | None = None,
    stats_service: Any | None = None,
    job_runner: Any | None = None,
    rate_limiter: FixedWindowRateLimiter | None = None,
) -> Container:
    """Build the application container.

    Every argument is an override: when it is ``None`` the factory from
    :data:`FACTORIES` is used. The tests use the overrides to inject their
    own fakes.
    """
    settings = settings or get_settings()
    kwargs: dict[str, Any] = {"settings": settings}

    repository = repository if repository is not None else _call(FACTORIES["repository"], **kwargs)
    kwargs["repository"] = repository

    llm_extractor = (
        llm_extractor if llm_extractor is not None else _call(FACTORIES["llm_extractor"], **kwargs)
    )
    kwargs["llm_extractor"] = llm_extractor

    tier1_extractor = (
        tier1_extractor
        if tier1_extractor is not None
        else _call(FACTORIES["tier1_extractor"], **kwargs)
    )
    kwargs["tier1_extractor"] = tier1_extractor

    validator = validator if validator is not None else _call(FACTORIES["validator"], **kwargs)
    kwargs["validator"] = validator

    search_service = (
        search_service
        if search_service is not None
        else _call(FACTORIES["search_service"], **kwargs)
    )
    alternatives_service = (
        alternatives_service
        if alternatives_service is not None
        else _call(FACTORIES["alternatives_service"], **kwargs)
    )
    bom_service = (
        bom_service if bom_service is not None else _call(FACTORIES["bom_service"], **kwargs)
    )
    review_service = (
        review_service
        if review_service is not None
        else _call(FACTORIES["review_service"], **kwargs)
    )
    stats_service = (
        stats_service if stats_service is not None else _call(FACTORIES["stats_service"], **kwargs)
    )
    job_runner = job_runner if job_runner is not None else _call(FACTORIES["job_runner"], **kwargs)

    if rate_limiter is None:
        rate_limiter = FixedWindowRateLimiter(limit=settings.search_rate_limit_per_minute)

    return Container(
        settings=settings,
        repository=repository,
        search_service=search_service,
        alternatives_service=alternatives_service,
        bom_service=bom_service,
        review_service=review_service,
        stats_service=stats_service,
        llm_extractor=llm_extractor,
        tier1_extractor=tier1_extractor,
        validator=validator,
        job_runner=job_runner,
        rate_limiter=rate_limiter,
    )


__all__ = ["FACTORIES", "build_container"]
