"""The composition root of the API.

This is the one file that decides which implementation of every protocol the
API uses.

Two wirings live here:

* :func:`build_container` - the **production** wiring. It uses the real
  repository (SQLite), the real tier 1 extractor, the real validator and the
  real services. The LLM extractor is built lazily, so the API starts even
  when no API key is configured; only a search that needs the model fails.
* :func:`build_fake_container` - the **offline** wiring. It uses the in-memory
  fakes of :mod:`app.fakes`, so the API and the frontend can be demonstrated
  without a database and without a key.

Switch with the ``PARTPILOT_WIRING`` environment variable:

* ``real`` (the default) - the production wiring.
* ``fake`` - the in-memory fakes.

Every factory may accept any subset of the keyword arguments ``settings``,
``repository``, ``llm_extractor``, ``tier1_extractor`` and ``validator``;
only the ones it declares are passed.
"""

from __future__ import annotations

import inspect
import logging
import os
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

logger = logging.getLogger("partpilot.api")

Factory = Callable[..., Any]


# ---------------------------------------------------------------- real wiring


def _real_repository(settings: Settings, **_: Any) -> Any:
    """The real repository on SQLite, with the seed data loaded."""
    from db.repository import SqlAlchemyPartsRepository
    from db.seed import load_seed
    from db.session import create_engine_for_url, init_db
    from integration.datasheet_seed import seed_datasheet_parts

    settings.ensure_dirs()
    engine = create_engine_for_url(settings.database_url, echo=settings.sql_echo)
    init_db(engine)
    summary = load_seed(engine)
    # The parts whose values are read from a datasheet. They are extracted
    # with the real pipeline, so the source viewer has a page to show.
    seed_datasheet_parts(engine, settings)
    logger.info(
        "database ready: %s parts, %s parameters",
        summary.get("parts"),
        summary.get("parameters"),
    )
    return SqlAlchemyPartsRepository(engine)


def _real_llm(settings: Settings, repository: Any = None, **_: Any) -> Any:
    """The real LLM extractor. The model is built on the first call."""
    from extraction.llm.extractor import LLMExtractorImpl

    return LLMExtractorImpl(settings=settings, recorder=_RepositoryRecorder(repository))


def _real_tier1(settings: Settings, **_: Any) -> Any:
    """The real rule based extractor."""
    from extraction.tier1.extractor import PdfTier1Extractor

    return PdfTier1Extractor()


def _real_validator(settings: Settings, **_: Any) -> Any:
    """The real validator."""
    from validation.validator import ParameterValidator

    return ParameterValidator()


def _real_search_service(repository: Any, llm_extractor: Any, **_: Any) -> Any:
    """The real search service."""
    from services.search import SearchService

    return SearchService(repository, llm_extractor)


def _real_alternatives_service(repository: Any, llm_extractor: Any, **_: Any) -> Any:
    """The real alternatives finder."""
    from services.alternatives import AlternativesService

    return AlternativesService(repository, llm_extractor)


def _real_bom_service(repository: Any, **_: Any) -> Any:
    """The real BOM health check."""
    from services.bom import BomService

    return BomService(repository)


def _real_review_service(repository: Any, **_: Any) -> Any:
    """The real review service."""
    from services.review import ReviewService

    return ReviewService(repository)


def _real_stats_service(repository: Any, **_: Any) -> Any:
    """The real statistics service."""
    from services.stats import StatsService

    return StatsService(repository)


def _real_job_runner(
    repository: Any,
    tier1_extractor: Any,
    llm_extractor: Any,
    validator: Any,
    **_: Any,
) -> Any:
    """The real background job runner."""
    from services.jobs import BackgroundJobRunner

    return BackgroundJobRunner(
        repository,
        tier1=tier1_extractor,
        llm=llm_extractor,
        validator=validator,
    )


class _RepositoryRecorder:
    """Forward the LLM call records to the repository.

    The LLM extractor records every call for the cost accounting of NFR-05.
    The repository owns the ``llm_calls`` table, so the recorder is a thin
    adapter that satisfies the recorder protocol of the LLM package.
    """

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def record(self, record: Any) -> None:
        if self._repository is None:
            return
        try:
            self._repository.record_llm_call(record)
        except Exception:  # pragma: no cover - the accounting must never break a call
            logger.exception("Could not record the LLM call")


# --------------------------------------------------------------- fake wiring


def _default_repository(settings: Settings, **_: Any) -> InMemoryPartsRepository:
    """The fake repository."""
    return InMemoryPartsRepository(settings)


def _default_llm(settings: Settings, **_: Any) -> StubLLMExtractor:
    """The fake LLM extractor."""
    return StubLLMExtractor()


def _default_tier1(settings: Settings, **_: Any) -> StubTier1Extractor:
    """The fake tier 1 extractor."""
    return StubTier1Extractor()


def _default_validator(settings: Settings, **_: Any) -> StubValidator:
    """The fake validator."""
    return StubValidator()


def _default_search_service(repository: Any, llm_extractor: Any, **_: Any) -> FakeSearchService:
    """The fake search service."""
    return FakeSearchService(repository, llm_extractor)


def _default_alternatives_service(
    repository: Any, llm_extractor: Any, **_: Any
) -> FakeAlternativesService:
    """The fake alternatives service."""
    return FakeAlternativesService(repository, llm_extractor)


def _default_bom_service(repository: Any, **_: Any) -> FakeBomService:
    """The fake BOM service."""
    return FakeBomService(repository)


def _default_review_service(repository: Any, **_: Any) -> FakeReviewService:
    """The fake review service."""
    return FakeReviewService(repository)


def _default_stats_service(repository: Any, **_: Any) -> FakeStatsService:
    """The fake statistics service."""
    return FakeStatsService(repository)


def _default_job_runner(repository: Any, tier1_extractor: Any, **_: Any) -> FakeJobRunner:
    """The fake job runner."""
    return FakeJobRunner(repository, tier1_extractor)


#: The production wiring.
REAL_FACTORIES: dict[str, Factory] = {
    "repository": _real_repository,
    "llm_extractor": _real_llm,
    "tier1_extractor": _real_tier1,
    "validator": _real_validator,
    "search_service": _real_search_service,
    "alternatives_service": _real_alternatives_service,
    "bom_service": _real_bom_service,
    "review_service": _real_review_service,
    "stats_service": _real_stats_service,
    "job_runner": _real_job_runner,
}

#: The offline wiring. It is the default of the test suite.
FAKE_FACTORIES: dict[str, Factory] = {
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

#: The factories of the composition root. The integration phase swaps the
#: entries here - and only here - for the real implementations.
FACTORIES: dict[str, Factory] = dict(REAL_FACTORIES)


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
    factories: dict[str, Factory] | None = None,
) -> Container:
    """Build the application container.

    Every argument is an override: when it is ``None`` the factory from
    :data:`FACTORIES` is used. The tests use the overrides to inject their
    own fakes.
    """
    settings = settings or get_settings()
    factories = FACTORIES if factories is None else factories
    kwargs: dict[str, Any] = {"settings": settings}

    repository = repository if repository is not None else _call(factories["repository"], **kwargs)
    kwargs["repository"] = repository

    llm_extractor = (
        llm_extractor if llm_extractor is not None else _call(factories["llm_extractor"], **kwargs)
    )
    kwargs["llm_extractor"] = llm_extractor

    tier1_extractor = (
        tier1_extractor
        if tier1_extractor is not None
        else _call(factories["tier1_extractor"], **kwargs)
    )
    kwargs["tier1_extractor"] = tier1_extractor

    validator = validator if validator is not None else _call(factories["validator"], **kwargs)
    kwargs["validator"] = validator

    search_service = (
        search_service
        if search_service is not None
        else _call(factories["search_service"], **kwargs)
    )
    alternatives_service = (
        alternatives_service
        if alternatives_service is not None
        else _call(factories["alternatives_service"], **kwargs)
    )
    bom_service = (
        bom_service if bom_service is not None else _call(factories["bom_service"], **kwargs)
    )
    review_service = (
        review_service
        if review_service is not None
        else _call(factories["review_service"], **kwargs)
    )
    stats_service = (
        stats_service if stats_service is not None else _call(factories["stats_service"], **kwargs)
    )
    job_runner = job_runner if job_runner is not None else _call(factories["job_runner"], **kwargs)

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


def build_fake_container(settings: Settings | None = None, **kwargs: Any) -> Container:
    """Build the container with the in-memory fakes."""
    kwargs.setdefault("factories", FAKE_FACTORIES)
    return build_container(settings, **kwargs)


def wiring_mode() -> str:
    """Return the wiring the environment asks for: ``real`` or ``fake``."""
    return os.getenv("PARTPILOT_WIRING", "real").strip().lower() or "real"


__all__ = [
    "FACTORIES",
    "FAKE_FACTORIES",
    "REAL_FACTORIES",
    "build_container",
    "build_fake_container",
    "wiring_mode",
]
