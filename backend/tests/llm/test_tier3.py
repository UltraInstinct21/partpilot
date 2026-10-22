"""Tier 3: the same extraction over a rendered page image."""

from __future__ import annotations

from extraction.llm import LLMExtractorImpl
from shared.schemas import ExtractionMethod, Family

from .conftest import PNG_1X1, make_tool_model

DRIVER_PAYLOAD = {
    "supply_voltage_max": {
        "value": 18.0,
        "unit": "V",
        "condition": {"temp": "25 C"},
        "page": 4,
        "raw_text": "Supply Voltage (V) | 4.5 | 18 | V",
        "confidence": 0.8,
    },
    "peak_source_current": {
        "value": 2.0,
        "unit": "A",
        "condition": {},
        "page": 4,
        "raw_text": "Peak Source Current | 2 | A",
        "confidence": 0.75,
    },
    "propagation_delay": None,
}


def _extractor(model, recorder, settings):
    return LLMExtractorImpl(model=model, recorder=recorder, settings=settings)


def test_tier3_reads_the_page_image(settings, recorder) -> None:
    model = make_tool_model(DRIVER_PAYLOAD, "GateDriverSpec")
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier3([(4, PNG_1X1)], Family.GATE_DRIVER, part_id="p2")

    assert result.method == ExtractionMethod.TIER3
    assert result.scanned is True
    assert result.pages_used == [4]
    by_name = {value.name: value for value in result.values}
    assert set(by_name) == {"supply_voltage_max", "peak_source_current"}
    vds = by_name["supply_voltage_max"]
    assert vds.value == 18.0
    assert vds.unit == "V"
    assert vds.page == 4
    assert vds.method == ExtractionMethod.TIER3
    assert vds.confidence > 0
    assert vds.condition == {"temp": "25 C"}


def test_tier3_reports_a_missing_field_as_failed(settings, recorder) -> None:
    model = make_tool_model(DRIVER_PAYLOAD, "GateDriverSpec")
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier3([(4, PNG_1X1)], Family.GATE_DRIVER)

    assert "propagation_delay" in result.failed_fields
    assert all(value.name != "propagation_delay" for value in result.values)


def test_tier3_records_one_call_per_page(settings, recorder) -> None:
    model = make_tool_model(DRIVER_PAYLOAD, "GateDriverSpec")
    extractor = _extractor(model, recorder, settings)

    extractor.extract_tier3([(4, PNG_1X1), (5, PNG_1X1)], Family.GATE_DRIVER)

    assert len(recorder.records) == 2
    assert {record.chain for record in recorder.records} == {"tier3_vision"}
    assert all(record.prompt_version == "v1" for record in recorder.records)
    assert all(record.cost > 0 for record in recorder.records)


def test_tier3_without_images_fails_every_field(settings, recorder) -> None:
    model = make_tool_model(DRIVER_PAYLOAD, "GateDriverSpec")
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier3([], Family.GATE_DRIVER)

    assert result.values == []
    assert "supply_voltage_max" in result.failed_fields
    assert recorder.records == []
