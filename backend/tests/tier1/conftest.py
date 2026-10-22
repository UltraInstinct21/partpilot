"""Shared fixtures for the tier-1 tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "contracts" / "fixtures"
PDF_DIR = FIXTURES / "pdfs"
PAGES_DIR = FIXTURES / "pages"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def pdf_dir() -> Path:
    return PDF_DIR


@pytest.fixture(scope="session")
def pages_dir() -> Path:
    return PAGES_DIR


@pytest.fixture(scope="session")
def expected_values() -> dict:
    return json.loads((PDF_DIR / "expected_values.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def page_samples() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(PAGES_DIR.glob("page_*.json"))
    ]
