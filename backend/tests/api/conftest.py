"""Shared fixtures for the API tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rate_limit import FixedWindowRateLimiter
from shared.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def settings() -> Settings:
    """A settings object for the tests."""
    return Settings(_env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A test client for the default (fully faked) application."""
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_factory(settings: Settings):
    """Build a test client with a replaced rate limit.

    The rate limit of ``POST /api/search`` is protected by the settings, so a
    test can build a client with a very small budget.
    """

    def build(limit: int = 2) -> TestClient:
        app = create_app(
            settings=settings,
            rate_limiter=FixedWindowRateLimiter(limit=limit),
        )
        return TestClient(app)

    return build
