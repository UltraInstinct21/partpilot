"""Test helpers for the LLM chains.

Every test uses a **fake** chat model. No test ever opens a network connection
and no test ever creates a real provider client (rule 2 of the project).
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage

from shared.config import Settings
from shared.schemas import LLMCallRecord

# A 1x1 transparent PNG - enough to build a vision message.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeToolChatModel(FakeMessagesListChatModel):
    """A fake chat model that answers with a tool call.

    ``langchain_core``'s fake models do not implement ``bind_tools``, so
    ``with_structured_output`` cannot be used with them as they are. This
    subclass adds the missing piece and nothing else.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakeToolChatModel:
        """Ignore the tool binding - the answers are canned."""
        return self


def tool_message(
    payload: dict[str, Any],
    schema_name: str = "MosfetSpec",
    tokens_in: int = 120,
    tokens_out: int = 30,
) -> AIMessage:
    """Return an AI message that carries a tool call with ``payload``."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": schema_name,
                "args": payload,
                "id": "call_1",
                "type": "tool_call",
            }
        ],
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    )


def text_message(content: str, tokens_in: int = 200, tokens_out: int = 20) -> AIMessage:
    """Return an AI message with plain text and usage metadata."""
    return AIMessage(
        content=content,
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    )


def make_tool_model(payload: dict[str, Any], schema_name: str = "MosfetSpec") -> FakeToolChatModel:
    """Return a fake model that always answers with the given tool call."""
    return FakeToolChatModel(responses=[tool_message(payload, schema_name)])


def make_text_model(content: str) -> GenericFakeChatModel:
    """Return a fake model that always answers with the given text."""
    return GenericFakeChatModel(messages=iter([text_message(content)]))


class RecordingRecorder:
    """A recorder that keeps every call in a list."""

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def record(self, record: LLMCallRecord) -> None:
        self.records.append(record)

    @property
    def last(self) -> LLMCallRecord:
        return self.records[-1]


class FakeRepository:
    """A duck typed repository that only stores the llm calls."""

    def __init__(self) -> None:
        self.calls: list[LLMCallRecord] = []

    def record_llm_call(self, record: LLMCallRecord) -> None:
        self.calls.append(record)


@pytest.fixture(autouse=True)
def _reset_global_llm_cache():
    """Never let a cached answer of one test leak into the next one."""
    from langchain_core.globals import set_llm_cache

    set_llm_cache(None)
    yield
    set_llm_cache(None)


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Settings that never touch the network and never write outside tmp."""
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data" / "raw",
        pdf_dir=tmp_path / "data" / "pdfs",
        cache_dir=tmp_path / "data" / "cache",
        llm_cache_dir=tmp_path / "data" / "llm_cache",
        llm_cache_enabled=False,
    )


@pytest.fixture
def recorder() -> RecordingRecorder:
    """A recorder that collects the calls."""
    return RecordingRecorder()
