"""The name mapper proposes, it never approves."""

from __future__ import annotations

from extraction.llm import LLMExtractorImpl
from shared.schemas import Family

from .conftest import make_tool_model


def _extractor(model, recorder, settings):
    return LLMExtractorImpl(model=model, recorder=recorder, settings=settings)


def test_the_proposed_name_is_returned(settings, recorder) -> None:
    model = make_tool_model(
        {"standard_name": "rds_on", "confidence": 0.9, "reason": "same symbol"},
        "NameMappingProposal",
    )
    extractor = _extractor(model, recorder, settings)

    assert extractor.map_name("RDS(on)", Family.MOSFET) == "rds_on"
    assert len(recorder.records) == 1
    record = recorder.last
    assert record.chain == "name_mapper"
    assert record.prompt_version == "v1"


def test_no_proposal_returns_none(settings, recorder) -> None:
    model = make_tool_model(
        {"standard_name": None, "confidence": 0.1, "reason": "unknown symbol"},
        "NameMappingProposal",
    )
    extractor = _extractor(model, recorder, settings)

    assert extractor.map_name("Quantum flux", Family.MOSFET) is None


def test_a_name_outside_the_allowed_list_returns_none(settings, recorder) -> None:
    model = make_tool_model(
        {"standard_name": "not_a_parameter", "confidence": 0.9, "reason": "?"},
        "NameMappingProposal",
    )
    extractor = _extractor(model, recorder, settings)

    assert extractor.map_name("RDS(on)", Family.MOSFET) is None


def test_a_low_confidence_returns_none(settings, recorder) -> None:
    model = make_tool_model(
        {"standard_name": "rds_on", "confidence": 0.2, "reason": "maybe"},
        "NameMappingProposal",
    )
    extractor = _extractor(model, recorder, settings)

    assert extractor.map_name("RDS(on)", Family.MOSFET) is None


def test_a_name_of_another_family_returns_none(settings, recorder) -> None:
    model = make_tool_model(
        {"standard_name": "rise_time", "confidence": 0.9, "reason": "driver slot"},
        "NameMappingProposal",
    )
    extractor = _extractor(model, recorder, settings)

    assert extractor.map_name("Rise Time", Family.MOSFET) is None
    assert extractor.map_name("Rise Time", Family.GATE_DRIVER) == "rise_time"
