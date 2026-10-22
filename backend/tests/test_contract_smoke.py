"""Smoke tests for the frozen contract layer.

This file is owned by the orchestrator. It only checks that the contract
loads and that the fixtures are well formed, so a broken contract fails fast
in every agent's branch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from shared import interfaces, schemas
from shared.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"
FIXTURES = CONTRACTS / "fixtures"


def test_schemas_expose_every_documented_model() -> None:
    for name in (
        "SourceRef",
        "ParameterValue",
        "PartRecord",
        "MosfetSpec",
        "GateDriverSpec",
        "ExtractionResult",
        "SearchFilter",
        "SearchResponse",
        "AlternativeResult",
        "BomLine",
        "BomRisk",
        "ReviewItem",
        "JobStatus",
        "StatsResponse",
        "LLMCallRecord",
    ):
        assert name in schemas.__all__, f"{name} is missing from shared.schemas"


def test_interfaces_expose_every_protocol() -> None:
    for name in (
        "Collector",
        "DatasheetDownloader",
        "Tier1Extractor",
        "LLMExtractor",
        "Validator",
        "PartsRepository",
        "SearchService",
        "AlternativesService",
        "BomService",
        "ReviewService",
        "JobRunner",
        "StatsService",
    ):
        assert name in interfaces.__all__, f"{name} is missing from shared.interfaces"


def test_settings_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.respect_robots_txt is True
    assert settings.download_delay_seconds >= 1.0
    assert settings.digikey_rate_limit_per_day <= 1000
    assert settings.mouser_rate_limit_per_minute <= 30
    assert "contact" in settings.user_agent


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_openapi_is_valid_and_lists_every_endpoint() -> None:
    spec = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.1")
    paths = spec["paths"]
    for path in (
        "/api/parts",
        "/api/parts/{part_id}",
        "/api/parts/{part_id}/sources/{param_id}",
        "/api/sources/{source_id}/page/{n}",
        "/api/search",
        "/api/parts/{part_id}/alternatives",
        "/api/bom/check",
        "/api/review",
        "/api/review/{param_id}",
        "/api/jobs/extract",
        "/api/jobs/{job_id}",
        "/api/stats",
    ):
        assert path in paths, f"{path} is missing from the OpenAPI contract"


@pytest.mark.parametrize(
    "relative",
    [
        "digikey/product_details.json",
        "digikey/keyword_search.json",
        "digikey/parts.json",
        "nexar/supply_response.json",
        "nexar/parts.json",
        "mouser/partnumber_search.json",
        "mouser/parts.json",
        "seed/parts.json",
        "pdfs/expected_values.json",
    ],
)
def test_fixture_is_valid_json(relative: str) -> None:
    payload = json.loads((FIXTURES / relative).read_text(encoding="utf-8"))
    assert payload


def test_seed_has_thirty_parts() -> None:
    payload = json.loads((FIXTURES / "seed" / "parts.json").read_text(encoding="utf-8"))
    parts = payload["parts"]
    assert len(parts) == 30
    families = {p["family"] for p in parts}
    assert families == {"mosfet", "gate_driver"}


def test_page_samples_exist() -> None:
    pages = sorted((FIXTURES / "pages").glob("page_*.json"))
    assert len(pages) == 5


def test_synthetic_pdfs_exist_and_are_small() -> None:
    for name in ("synthetic_mosfet.pdf", "synthetic_gate_driver.pdf", "synthetic_scanned.pdf"):
        path = FIXTURES / "pdfs" / name
        assert path.exists(), f"{name} is missing"
        assert path.stat().st_size < 200_000, f"{name} is too large for the repository"
        assert path.read_bytes()[:5] == b"%PDF-"


def test_scanned_pdf_has_no_text_layer() -> None:
    import pdfplumber

    with pdfplumber.open(FIXTURES / "pdfs" / "synthetic_scanned.pdf") as pdf:
        for page in pdf.pages:
            assert not (page.extract_text() or "").strip()


def test_gold_set_example_is_a_csv_with_a_header() -> None:
    text = (FIXTURES / "gold" / "gold_set_example.csv").read_text(encoding="utf-8")
    header = text.splitlines()[0]
    for column in ("part_id", "mpn", "param_name", "value", "unit"):
        assert column in header
