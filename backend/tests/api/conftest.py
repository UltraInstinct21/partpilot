"""Shared fixtures for the API tests.

The tests use the **fake** wiring, so they never touch the database and never
need a key. The production wiring is covered by the integration test in
``backend/tests/integration/``.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rate_limit import FixedWindowRateLimiter
from app.wiring import build_fake_container
from shared.config import Settings


@pytest.fixture
def settings() -> Settings:
    """A settings object for the tests."""
    return Settings(_env_file=None)


@pytest.fixture(autouse=True)
def _no_live_scraper():
    """Prevent the inline WebDiscoveryService in the parts route from making
    real HTTP requests during tests.  deep_scrape_part returns None so the
    route falls through to the repository result as normal."""
    mock_web = MagicMock()
    mock_web.deep_scrape_part.return_value = None
    with patch("services.web_search.WebDiscoveryService", return_value=mock_web):
        yield


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A test client for the application with the in-memory fakes."""
    app = create_app(container=build_fake_container(settings))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_factory(settings: Settings):
    """Build a test client with a replaced rate limit.

    The rate limit of ``POST /api/search`` is protected by the settings, so a
    test can build a client with a very small budget.
    """

    def build(limit: int = 2) -> TestClient:
        container = build_fake_container(settings, rate_limiter=FixedWindowRateLimiter(limit=limit))
        return TestClient(create_app(container=container))

    return build
