"""End to end tests of the tier-1 extractor against the frozen fixtures.

Every value of ``contracts/fixtures/pdfs/expected_values.json`` must be
reproduced exactly (value, value_min/typ/max, unit, page) and nothing may be
invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from extraction.tier1 import PdfTier1Extractor
from extraction.tier1.namemap import NameMap
from shared.schemas import ExtractionMethod, ExtractionResult, Family, ValueStatus

MOSFET = "pdfs/synthetic_mosfet.pdf"
GATE_DRIVER = "pdfs/synthetic_gate_driver.pdf"
SCANNED = "pdfs/synthetic_scanned.pdf"


def _assert_value(value, expected: dict) -> None:
    """Assert the fields the fixture records for one value."""
    for key in ("value", "value_min", "value_typ", "value_max"):
        if key in expected:
            assert getattr(value, key) == pytest.approx(expected[key]), f"{value.name}: {key}"
    if "unit" in expected:
        assert value.unit == expected["unit"], value.name
    if "page" in expected:
        assert value.page == expected["page"], value.name
    if "method" in expected:
        assert value.method == ExtractionMethod(expected["method"]), value.name
    if "condition" in expected:
        assert value.condition == expected["condition"], value.name


def _extract(fixtures_dir: Path, key: str, expected: dict) -> ExtractionResult:
    extractor = PdfTier1Extractor()
    return extractor.extract(
        str(fixtures_dir / key),
        Family(expected["family"]),
        source_id=expected["source_id"],
    )


def test_mosfet_pdf_values_match_the_fixture(fixtures_dir: Path, expected_values: dict) -> None:
    expected = expected_values[MOSFET]
    result = _extract(fixtures_dir, MOSFET, expected)

    assert result.method == ExtractionMethod.TIER1
    assert result.scanned is False
    assert result.family == Family.MOSFET
    assert result.source_id == expected["source_id"]

    produced = {value.name: value for value in result.values}
    assert set(produced) == set(expected["values"]), "the extractor missed or invented a field"

    for name, wanted in expected["values"].items():
        _assert_value(produced[name], wanted)


def test_gate_driver_pdf_values_match_the_fixture(
    fixtures_dir: Path, expected_values: dict
) -> None:
    expected = expected_values[GATE_DRIVER]
    result = _extract(fixtures_dir, GATE_DRIVER, expected)

    assert result.method == ExtractionMethod.TIER1
    assert result.scanned is False
    assert result.family == Family.GATE_DRIVER

    produced = {value.name: value for value in result.values}
    assert set(produced) == set(expected["values"]), "the extractor missed or invented a field"

    for name, wanted in expected["values"].items():
        _assert_value(produced[name], wanted)


def test_scanned_pdf_yields_no_value(fixtures_dir: Path, expected_values: dict) -> None:
    expected = expected_values[SCANNED]
    result = _extract(fixtures_dir, SCANNED, expected)

    assert result.scanned is True
    assert result.values == []
    assert result.method == ExtractionMethod.TIER1
    assert result.notes and "tier 3" in result.notes.lower()


def test_every_value_carries_its_provenance(fixtures_dir: Path, expected_values: dict) -> None:
    result = _extract(fixtures_dir, MOSFET, expected_values[MOSFET])
    assert result.values
    for value in result.values:
        assert value.page is not None
        assert value.source_id == expected_values[MOSFET]["source_id"]
        assert value.method == ExtractionMethod.TIER1
        assert value.status == ValueStatus.REVIEW
        assert 0.0 <= value.confidence <= 1.0
        assert value.raw_text


def test_a_value_carries_the_condition_of_its_row(
    fixtures_dir: Path, expected_values: dict
) -> None:
    result = _extract(fixtures_dir, MOSFET, expected_values[MOSFET])
    produced = {value.name: value for value in result.values}

    assert produced["rds_on"].condition == {"Vgs": "10 V", "Id": "10 A", "Tj": "25 C"}
    assert produced["vgs_threshold"].condition == {"Id": "250 uA"}
    # a row without a condition cell has an empty condition, never a guess
    assert produced["thermal_resistance"].condition == {}


def test_pages_used_are_the_pages_of_the_values(fixtures_dir: Path, expected_values: dict) -> None:
    result = _extract(fixtures_dir, MOSFET, expected_values[MOSFET])
    assert result.pages_used == [1, 2]


def test_find_pages_of_the_mosfet_pdf(pdf_dir: Path) -> None:
    extractor = PdfTier1Extractor()
    pages = extractor.find_pages(str(pdf_dir / "synthetic_mosfet.pdf"))
    assert pages == [1, 2]


def test_the_family_is_inferred_when_it_is_not_given(fixtures_dir: Path) -> None:
    extractor = PdfTier1Extractor()
    mosfet = extractor.extract(str(fixtures_dir / MOSFET))
    assert mosfet.family == Family.MOSFET
    driver = extractor.extract(str(fixtures_dir / GATE_DRIVER))
    assert driver.family == Family.GATE_DRIVER


def test_a_missing_field_is_reported_as_failed(fixtures_dir: Path) -> None:
    extractor = PdfTier1Extractor()
    result = extractor.extract(str(fixtures_dir / MOSFET), Family.MOSFET)
    # the synthetic MOSFET has no package row
    assert result.failed_fields == ["package"]


def test_an_unknown_row_is_skipped_silently(fixtures_dir: Path) -> None:
    """A row that is not a known parameter never becomes a value."""
    extractor = PdfTier1Extractor()
    result = extractor.extract(str(fixtures_dir / MOSFET), Family.MOSFET)
    names = {value.name for value in result.values}
    assert "total_doom_resistance" not in names
    assert "comment" not in names


def test_an_injected_name_map_is_used(fixtures_dir: Path) -> None:
    """The database agent can inject its own name_map table."""
    table = {"RDS(ON)": "rds_on"}

    def lookup(raw_name: str) -> str | None:
        return table.get(raw_name)

    extractor = PdfTier1Extractor(name_map=NameMap(lookup))
    result = extractor.extract(str(fixtures_dir / MOSFET), Family.MOSFET)
    produced = {value.name: value for value in result.values}
    assert produced["rds_on"].value == pytest.approx(5.5)
