"""Shared fixtures of the collector tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from shared.config import REPO_ROOT, Settings

FIXTURES = REPO_ROOT / "contracts" / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return a settings object that writes into the temporary directory."""
    data_dir = tmp_path / "data"
    return Settings(
        _env_file=None,
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        pdf_dir=data_dir / "pdfs",
        cache_dir=data_dir / "cache",
        llm_cache_dir=data_dir / "llm_cache",
        db_path=data_dir / "partpilot.db",
        # keep the tests fast
        retry_backoff_seconds=0.001,
        max_retries=3,
        digikey_client_id="test-client",
        digikey_client_secret="test-secret",
        nexar_client_id="test-client",
        nexar_client_secret="test-secret",
        mouser_api_key="test-key",
    )


@pytest.fixture
def fixture_dir() -> Path:
    """Return the directory with the recorded API responses."""
    return FIXTURES


def load_fixture(relative: str) -> Any:
    """Load one recorded fixture."""
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def load() -> Callable[[str], Any]:
    """Return the loader of the recorded fixtures."""
    return load_fixture
