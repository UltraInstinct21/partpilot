"""Tests of the scanned PDF detection."""

from __future__ import annotations

from pathlib import Path

from extraction.tier1.scanned import is_scanned, page_text_stats


def test_the_scanned_pdf_is_detected(pdf_dir: Path) -> None:
    assert is_scanned(str(pdf_dir / "synthetic_scanned.pdf")) is True


def test_a_datasheet_with_text_is_not_scanned(pdf_dir: Path) -> None:
    assert is_scanned(str(pdf_dir / "synthetic_mosfet.pdf")) is False
    assert is_scanned(str(pdf_dir / "synthetic_gate_driver.pdf")) is False


def test_text_statistics(pdf_dir: Path) -> None:
    stats = page_text_stats(str(pdf_dir / "synthetic_mosfet.pdf"))
    assert stats["pages"] == 2
    assert stats["chars"] > 100
    assert stats["chars_per_page"] > 20
