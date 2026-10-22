"""A deterministic stand-in for the tier 1 (rule based) PDF extractor.

The stub implements the ``Tier1Extractor`` protocol of ``shared.interfaces``.
It never opens a PDF and never guesses a value: it returns a fixed, clearly
marked result so the job pipeline can be exercised end to end.
"""

from __future__ import annotations

from pathlib import Path

from shared.schemas import ExtractionMethod, ExtractionResult, Family, ParameterValue


class StubTier1Extractor:
    """Returns a canned extraction result."""

    name = "stub-tier1"

    def extract(self, pdf_path: str, family: Family | None = None) -> ExtractionResult:
        """Return a canned result for ``pdf_path``."""
        exists = bool(pdf_path) and Path(pdf_path).exists()
        values: list[ParameterValue] = []
        if exists and family == Family.MOSFET:
            values = [
                ParameterValue(
                    name="vds_max",
                    value=100.0,
                    unit="V",
                    page=1,
                    method=ExtractionMethod.TIER1,
                    confidence=0.85,
                ),
                ParameterValue(
                    name="rds_on",
                    value=5.5,
                    unit="mohm",
                    page=2,
                    method=ExtractionMethod.TIER1,
                    confidence=0.85,
                ),
            ]
        elif exists and family == Family.GATE_DRIVER:
            values = [
                ParameterValue(
                    name="supply_voltage_max",
                    value=18.0,
                    unit="V",
                    page=1,
                    method=ExtractionMethod.TIER1,
                    confidence=0.85,
                )
            ]
        return ExtractionResult(
            method=ExtractionMethod.TIER1,
            family=family,
            values=values,
            pages_used=[1, 2] if exists else [],
            failed_fields=[] if values else ["no_pdf"],
            notes="Stub extractor: canned values, no PDF was parsed.",
            duration_ms=0,
        )

    def find_pages(self, pdf_path: str) -> list[int]:
        """Return the page numbers that hold characteristics tables."""
        if not pdf_path or not Path(pdf_path).exists():
            return []
        return [1, 2]


__all__ = ["StubTier1Extractor"]
