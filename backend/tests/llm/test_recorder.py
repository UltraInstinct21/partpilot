"""Every LLM call must be recorded with its tokens, its cost and its prompt."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from extraction.llm.recorder import (
    CallRecorder,
    NoOpRecorder,
    build_call_record,
    estimate_cost,
    usage_from_response,
)
from shared.schemas import LLMCallRecord

from .conftest import FakeRepository, text_message


def test_cost_uses_the_settings(settings) -> None:
    settings.llm_cost_per_million_input = 1.0
    settings.llm_cost_per_million_output = 10.0
    assert estimate_cost(1_000_000, 0, settings) == pytest.approx(1.0)
    assert estimate_cost(0, 1_000_000, settings) == pytest.approx(10.0)
    assert estimate_cost(500_000, 100_000, settings) == pytest.approx(1.5)


def test_usage_is_read_from_the_response() -> None:
    message = text_message("hello", tokens_in=11, tokens_out=7)
    assert usage_from_response(message) == (11, 7)


def test_usage_is_zero_when_there_is_no_metadata() -> None:
    assert usage_from_response(AIMessage(content="x")) == (0, 0)
    assert usage_from_response(None) == (0, 0)


def test_build_call_record_computes_the_cost(settings) -> None:
    settings.llm_cost_per_million_input = 0.15
    settings.llm_cost_per_million_output = 0.60
    record = build_call_record(
        chain="tier2_extractor",
        model="gpt-4o-mini",
        response=text_message("x", tokens_in=1_000_000, tokens_out=1_000_000),
        prompt_version="v1",
        part_id="p1",
        cached=False,
        duration_ms=123,
        settings=settings,
    )
    assert isinstance(record, LLMCallRecord)
    assert record.tokens_in == 1_000_000
    assert record.tokens_out == 1_000_000
    assert record.cost == pytest.approx(0.75)
    assert record.prompt_version == "v1"
    assert record.part_id == "p1"
    assert record.cached is False
    assert record.duration_ms == 123


def test_call_recorder_keeps_and_forwards_the_records(settings) -> None:
    repository = FakeRepository()
    recorder = CallRecorder(repository=repository, settings=settings)
    record = build_call_record(chain="tier2_extractor", model="m", settings=settings)
    recorder.record(record)
    assert recorder.records == [record]
    assert repository.calls == [record]
    assert recorder.total_cost == record.cost


def test_noop_recorder_does_nothing() -> None:
    recorder = NoOpRecorder()
    record = build_call_record(chain="c", model="m")
    assert recorder.record(record) is None
