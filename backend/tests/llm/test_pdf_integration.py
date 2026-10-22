"""The tier 2 chain over a real (synthetic) datasheet PDF.

The PDF is a fixture of the frozen contract. No network, no provider: the
model is a fake one that answers with a fixed table.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from extraction.llm import LLMExtractorImpl
from shared.schemas import Family

from .conftest import make_tool_model

REPO_ROOT = Path(__file__).resolve().parents[3]
PDF = REPO_ROOT / "contracts" / "fixtures" / "pdfs" / "synthetic_mosfet.pdf"

PAYLOAD = {
    "rds_on": {
        "value": 45.0,
        "unit": "mOhm",
        "condition": {"vgs": "10 V", "id": "10 A"},
        "page": 1,
        "raw_text": "RDS(on) | 35 | 45 | 55 | mOhm",
        "confidence": 0.8,
    },
    "vds_max": None,
}


def _pages() -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    with pymupdf.open(PDF) as document:
        for number, page in enumerate(document, start=1):
            pages.append((number, page.get_text() or ""))
    return pages


def test_the_extraction_runs_over_the_pages_of_the_pdf(settings, recorder) -> None:
    pages = _pages()
    assert pages, "the fixture PDF has no text"

    model = make_tool_model(PAYLOAD)
    extractor = LLMExtractorImpl(model=model, recorder=recorder, settings=settings)
    result = extractor.extract_tier2(pages, Family.MOSFET, part_id="synthetic-1")

    assert result.method.value == "tier2"
    names = {value.name for value in result.values}
    assert names == {"rds_on"}
    assert result.values[0].page == 1
    assert result.values[0].condition == {"vgs": "10 V", "id": "10 A"}
    assert "vds_max" in result.failed_fields
    assert recorder.records[-1].chain == "tier2_extractor"
