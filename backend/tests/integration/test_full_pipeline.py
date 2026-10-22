"""The full pipeline, from a datasheet PDF to the HTTP response.

This is the integration test of the plan (section 14, quality check 3): "Write
an integration test for one full datasheet."

The chain that is exercised:

    synthetic PDF
        -> tier 1 extraction            (backend/extraction/tier1)
        -> validation                    (backend/validation)
        -> SQLite                        (backend/db)
        -> search + alternatives         (backend/services)
        -> HTTP response                 (backend/app)
        -> the OpenAPI contract          (contracts/openapi.yaml)

Every step uses the real implementation. The only fake is the LLM filter
builder, because a real model call is not allowed in a test (NFR-02, NFR-05).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from shared.config import Settings
from shared.schemas import (
    ExtractionMethod,
    Family,
    ParameterConstraint,
    SearchFilter,
    SourceRef,
    SourceType,
    ValueStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"
MOSFET_PDF = REPO_ROOT / "contracts" / "fixtures" / "pdfs" / "synthetic_mosfet.pdf"
EXPECTED = REPO_ROOT / "contracts" / "fixtures" / "pdfs" / "expected_values.json"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """A settings object with a database in a temporary directory."""
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        db_path=tmp_path / "integration.db",
        raw_dir=tmp_path / "raw",
        pdf_dir=tmp_path / "pdfs",
        cache_dir=tmp_path / "cache",
        llm_cache_dir=tmp_path / "llm_cache",
    )


@pytest.fixture
def pipeline(settings: Settings):
    """Build the real pipeline on a temporary database."""
    from db.repository import SqlAlchemyPartsRepository
    from db.session import create_engine_for_url, init_db
    from extraction.tier1.extractor import PdfTier1Extractor
    from services.alternatives import AlternativesService
    from services.search import SearchService
    from validation.validator import ParameterValidator

    settings.ensure_dirs()
    engine = create_engine_for_url(settings.database_url)
    init_db(engine)
    repository = SqlAlchemyPartsRepository(engine)
    return {
        "engine": engine,
        "repository": repository,
        "tier1": PdfTier1Extractor(),
        "validator": ParameterValidator(),
        "search": SearchService(repository),
        "alternatives": AlternativesService(repository),
    }


def test_the_whole_pipeline(settings: Settings, pipeline) -> None:
    """PDF -> tier 1 -> validate -> store -> search -> alternatives -> HTTP."""
    repository = pipeline["repository"]
    tier1 = pipeline["tier1"]
    validator = pipeline["validator"]

    # --- 1. tier 1 reads the datasheet ------------------------------------
    result = tier1.extract(str(MOSFET_PDF), Family.MOSFET, source_id="pdf-synthetic-mosfet")
    assert result.method == ExtractionMethod.TIER1
    assert result.scanned is False
    assert result.values, "tier 1 must read the characteristics table"
    assert "rds_on" not in result.failed_fields

    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))["pdfs/synthetic_mosfet.pdf"]
    expected_values = expected["values"]

    # Every value of the fixture is reproduced, with its page.
    for name, want in expected_values.items():
        got = next((v for v in result.values if v.name == name), None)
        assert got is not None, f"tier 1 did not read {name}"
        assert got.page == want["page"], f"{name} is on the wrong page"
        assert got.method == ExtractionMethod.TIER1

    # --- 2. the validator normalises the unit and checks the range --------
    values = validator.validate_many(result.values)
    by_name = {value.name: value for value in values}
    rds = by_name["rds_on"]
    # The PDF says 5.5 mOhm, the database stores the canonical unit.
    assert rds.value == pytest.approx(0.0055)
    assert rds.unit == "ohm"
    assert rds.status is ValueStatus.ACCEPTED
    assert rds.confidence > 0.75
    assert rds.source_id is not None
    assert rds.page == 2
    assert rds.condition, "the test condition travels with the value"

    # --- 3. the values are stored with their provenance --------------------
    source = SourceRef(
        source_id="pdf-synthetic-mosfet",
        url="https://example.invalid/datasheets/PMP100N08.pdf",
        type=SourceType.PDF,
        file_hash="synthetic",
        local_path=str(MOSFET_PDF),
        page_count=2,
    )
    repository.add_source(source)

    from shared.schemas import PartRecord

    part = PartRecord(
        part_id="mosfet-pmp100n08",
        mpn="PMP100N08",
        manufacturer="PartPilot Synthetic",
        family=Family.MOSFET,
        package="TO-220AB",
        lifecycle_status="active",
        datasheet_url="https://example.invalid/datasheets/PMP100N08.pdf",
        source_ids=[source.source_id],
    )
    for value in values:
        value.part_id = part.part_id
        value.source_id = source.source_id
    part.parameters = values
    repository.add_part(part)

    stored = repository.get_part("mosfet-pmp100n08")
    assert stored is not None
    assert len(stored.parameters) == len(values)
    stored_rds = next(v for v in stored.parameters if v.name == "rds_on")
    assert stored_rds.value == pytest.approx(0.0055)
    assert stored_rds.unit == "ohm"
    assert stored_rds.page == 2

    # --- 4. the search finds it through the database ----------------------
    search = pipeline["search"]
    response = search.search_filter(
        SearchFilter(
            family=Family.MOSFET,
            parameters=[ParameterConstraint(name="rds_on", unit="mohm", max=6.0, operator="lte")],
        )
    )
    assert response.total >= 1
    found = [part for part in response.results if part.part_id == "mosfet-pmp100n08"]
    assert found, "the extracted part must be found by the search"
    # The constraint was given in mohm and matched the canonical ohm value.
    assert found[0].key_parameters["rds_on"] == pytest.approx(0.0055)

    # --- 5. the alternatives need more than one part ----------------------
    from db.seed import load_seed

    load_seed(pipeline["engine"])
    alternatives = pipeline["alternatives"].alternatives("mosfet-pmp100n08", limit=5)
    assert alternatives, "the alternatives finder must return something"
    assert alternatives[0].rank == 1
    assert alternatives[0].reason

    # --- 6. the HTTP response matches the OpenAPI contract ----------------
    from app.main import create_app
    from app.wiring import build_fake_container

    container = build_fake_container(settings)
    # The real repository is the one that holds the extracted part.
    container.repository = repository
    client = TestClient(create_app(container=container))

    http = client.get("/api/parts", params={"family": "mosfet", "limit": 5})
    assert http.status_code == 200
    payload = http.json()

    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    schema = contract["components"]["schemas"]["SearchResponse"]
    assert set(schema["required"]) <= set(payload)
    for result_item in payload["results"]:
        item_schema = contract["components"]["schemas"]["PartSummary"]
        assert set(item_schema["required"]) <= set(result_item)

    # The response of the part itself carries the provenance of every value.
    part_response = client.get("/api/parts/mosfet-pmp100n08")
    assert part_response.status_code == 200
    body = part_response.json()
    for value in body["parameters"]:
        assert value["source_id"] == "pdf-synthetic-mosfet"
        assert value["page"] is not None
        assert value["method"] == "tier1"
        assert 0.0 <= value["confidence"] <= 1.0
        assert value["status"] in {"accepted", "review", "rejected"}

    # The source viewer can show the page the value came from.
    page = client.get("/api/sources/pdf-synthetic-mosfet/page/2")
    assert page.status_code == 200
    assert "Electrical Characteristics" in page.json()["text"]


def test_a_scanned_pdf_produces_no_values(settings: Settings, pipeline) -> None:
    """A PDF without a text layer must not produce a value (WP3, tier 3 path)."""
    scanned = REPO_ROOT / "contracts" / "fixtures" / "pdfs" / "synthetic_scanned.pdf"
    result = pipeline["tier1"].extract(str(scanned), Family.MOSFET)
    assert result.scanned is True
    assert result.values == []
