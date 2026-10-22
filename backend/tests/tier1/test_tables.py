"""Tests of the page finder and of the table extraction."""

from __future__ import annotations

import json
from pathlib import Path

from extraction.tier1.page_finder import find_pages, part_number_of
from extraction.tier1.rows import detect_schema, parse_row
from extraction.tier1.tables import extract_tables


def test_find_pages_finds_the_ratings_and_characteristics_pages(pdf_dir: Path) -> None:
    pages = find_pages(str(pdf_dir / "synthetic_mosfet.pdf"))
    assert 1 in pages, "the Absolute Maximum Ratings page is missing"
    assert 2 in pages, "the Electrical Characteristics page is missing"
    assert pages == sorted(pages), "the pages are not in document order"
    assert len(pages) == len(set(pages)), "the page list has duplicates"


def test_find_pages_returns_one_based_numbers(pdf_dir: Path) -> None:
    pages = find_pages(str(pdf_dir / "synthetic_mosfet.pdf"))
    assert all(page >= 1 for page in pages)


def test_find_pages_of_the_gate_driver(pdf_dir: Path) -> None:
    pages = find_pages(str(pdf_dir / "synthetic_gate_driver.pdf"))
    assert pages[0] == 1


def test_part_number_is_found(pdf_dir: Path) -> None:
    assert part_number_of(str(pdf_dir / "synthetic_mosfet.pdf")) == "PMP100N08"
    assert part_number_of(str(pdf_dir / "synthetic_gate_driver.pdf")) == "PGD35"


def test_tables_are_extracted_with_their_page(pdf_dir: Path) -> None:
    tables = extract_tables(str(pdf_dir / "synthetic_mosfet.pdf"))
    assert tables
    assert {table.page for table in tables} == {1, 2}
    for table in tables:
        assert table.rows
        assert all(isinstance(cell, str) for row in table.rows for cell in row)


def test_the_mosfet_table_has_the_expected_header(pdf_dir: Path) -> None:
    tables = extract_tables(str(pdf_dir / "synthetic_mosfet.pdf"))
    header = tables[0].rows[0]
    assert header[0] == "Parameter"
    assert header[1] == "Symbol"


def test_recorded_page_samples_are_parsed(pages_dir: Path) -> None:
    """The recorded page samples are the output of the page/table step."""
    samples = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(pages_dir.glob("page_*.json"))
    ]
    assert len(samples) == 5
    parsed_rows = 0
    for sample in samples:
        for table in sample["tables"]:
            schema = detect_schema(table["rows"])
            assert schema.header_index == 0
            start = schema.header_index + 1
            for row in table["rows"][start:]:
                parsed = parse_row(row, schema, sample["page"])
                assert parsed is not None
                assert parsed.label
                parsed_rows += 1
    assert parsed_rows == 24


def test_recorded_sample_rows_carry_their_values(pages_dir: Path) -> None:
    sample = json.loads((pages_dir / "page_02.json").read_text(encoding="utf-8"))
    table = sample["tables"][0]
    schema = detect_schema(table["rows"])
    row = parse_row(table["rows"][1], schema, sample["page"])
    assert row is not None
    assert row.label == "Drain-Source On-Resistance"
    assert row.symbol == "RDS(on)"
    assert row.values.typical == 5.5
    assert row.values.maximum == 7.0
    assert row.values.minimum is None
    assert row.unit == "mohm"
    assert row.conditions == {"Vgs": "10 V", "Id": "10 A", "Tj": "25 C"}


def test_scanned_page_sample_has_no_table(pages_dir: Path) -> None:
    sample = json.loads((pages_dir / "page_05.json").read_text(encoding="utf-8"))
    assert sample["tables"] == []
    assert sample["is_image_only"] is True
