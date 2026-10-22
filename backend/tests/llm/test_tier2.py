"""Tier 2: values, failed fields and the call record."""

from __future__ import annotations

import pytest

from extraction.llm import LLMExtractorImpl
from shared.schemas import ExtractionMethod, Family

from .conftest import FakeToolChatModel, make_tool_model, tool_message

MOSFET_PAYLOAD = {
    "vds_max": {
        "value": 100.0,
        "unit": "V",
        "condition": {"vgs": "10 V", "temp": "25 C"},
        "page": 3,
        "raw_text": "Drain-Source Voltage (V) | 100 | 200 | 250",
        "confidence": 0.9,
        "source_id": "src-1",
    },
    "rds_on": {
        "value": 45.0,
        "unit": "mOhm",
        "condition": {"vgs": "10 V", "id": "10 A"},
        "page": 3,
        "raw_text": "RDS(on) (mOhm) | 35 | 45 | 55",
        "confidence": 0.85,
    },
    "id_continuous": None,
}

PAGE_TEXT = """
Electrical Characteristics
| Symbol | Parameter | Min | Typ | Max | Unit |
| 1 | Drain-Source Voltage | 100 | | 250 | V |
"""


def _extractor(model, recorder, settings):
    return LLMExtractorImpl(model=model, recorder=recorder, settings=settings)


def test_tier2_returns_the_values_of_the_model(settings, recorder) -> None:
    model = make_tool_model(MOSFET_PAYLOAD)
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET, part_id="p1")

    assert result.method == ExtractionMethod.TIER2
    assert result.family == Family.MOSFET
    assert result.part_id == "p1"
    assert result.pages_used == [3]
    by_name = {value.name: value for value in result.values}
    assert set(by_name) == {"vds_max", "rds_on"}

    vds = by_name["vds_max"]
    assert vds.value == 100.0
    assert vds.unit == "V"
    assert vds.page == 3
    assert vds.method == ExtractionMethod.TIER2
    assert vds.condition == {"vgs": "10 V", "temp": "25 C"}
    assert vds.confidence > 0
    assert vds.source_id == "src-1"
    assert vds.raw_text.startswith("Drain-Source Voltage")

    rds = by_name["rds_on"]
    assert rds.value == 45.0
    assert rds.unit == "mOhm"
    assert rds.page == 3
    assert rds.confidence > 0


def test_tier2_reports_a_missing_field_as_failed(settings, recorder) -> None:
    model = make_tool_model(MOSFET_PAYLOAD)
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET)

    assert "id_continuous" in result.failed_fields
    assert "id_continuous" not in {value.name for value in result.values}
    # nothing was invented for the failed field
    assert all(value.name != "id_continuous" for value in result.values)
    # every other slot of the schema is failed as well, it was not in the text
    assert "vgs_threshold" in result.failed_fields


def test_tier2_without_a_value_never_uses_a_default(settings, recorder) -> None:
    payload = dict(MOSFET_PAYLOAD)
    payload["rds_on"] = {"value": None, "unit": "mOhm", "page": 3}
    model = make_tool_model(payload)
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET)

    assert "rds_on" in result.failed_fields
    assert all(value.name != "rds_on" for value in result.values)


def test_tier2_records_the_call(settings, recorder) -> None:
    model = make_tool_model(MOSFET_PAYLOAD)
    extractor = _extractor(model, recorder, settings)

    extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET, part_id="p1")

    assert len(recorder.records) == 1
    record = recorder.last
    assert record.chain == "tier2_extractor"
    assert record.model
    assert record.prompt_version == "v1"
    assert record.part_id == "p1"
    assert record.cached is False
    assert record.tokens_in == 120
    assert record.tokens_out == 30
    assert record.cost > 0
    assert record.duration_ms is not None


def test_tier2_reports_a_cached_call(settings, recorder) -> None:
    settings.llm_cache_enabled = True
    model = make_tool_model(MOSFET_PAYLOAD)
    extractor = _extractor(model, recorder, settings)

    first = extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET)
    second = extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET)

    assert len(recorder.records) == 2
    assert recorder.records[0].cached is False
    assert recorder.records[1].cached is True
    assert second.values == first.values


def test_tier2_without_pages_fails_every_field(settings, recorder) -> None:
    model = make_tool_model(MOSFET_PAYLOAD)
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier2([], Family.MOSFET)

    assert result.values == []
    assert "rds_on" in result.failed_fields
    assert recorder.records == []


def test_tier2_uses_the_gate_driver_schema(settings, recorder) -> None:
    payload = {
        "supply_voltage_max": {
            "value": 18.0,
            "unit": "V",
            "condition": {},
            "page": 2,
            "raw_text": "Supply Voltage | 4.5 | | 18 | V",
            "confidence": 0.8,
        },
        "rise_time": None,
    }
    model = make_tool_model(payload, "GateDriverSpec")
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier2([(2, "Supply Voltage")], Family.GATE_DRIVER)

    assert [value.name for value in result.values] == ["supply_voltage_max"]
    assert result.values[0].method == ExtractionMethod.TIER2
    assert "rise_time" in result.failed_fields


def test_tier2_survives_a_broken_answer(settings, recorder) -> None:
    model = FakeToolChatModel(responses=[tool_message({"rds_on": "not a number"})])
    extractor = _extractor(model, recorder, settings)

    result = extractor.extract_tier2([(3, PAGE_TEXT)], Family.MOSFET)

    assert result.values == []
    assert result.failed_fields
    assert len(recorder.records) == 1


@pytest.mark.parametrize("family", [Family.MOSFET, Family.GATE_DRIVER])
def test_the_extractor_implements_the_protocol(family) -> None:
    from shared.interfaces import LLMExtractor

    extractor = LLMExtractorImpl()
    assert isinstance(extractor, LLMExtractor)
