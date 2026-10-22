"""Recording of every LLM call (NFR-05, plan section 7 ``llm_calls``).

The recorder is **injected** into the extractor. The duck type is the one of
:class:`shared.schemas.LLMCallRecorder`::

    def record(self, record: LLMCallRecord) -> None: ...

:class:`CallRecorder` keeps the records in memory and forwards them to a
:class:`shared.interfaces.PartsRepository` (which has ``record_llm_call``) as
soon as one is available. The repository is optional so the extraction code
never depends on the database.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from shared.config import Settings, get_settings
from shared.schemas import LLMCallRecord

logger = logging.getLogger(__name__)


@runtime_checkable
class Recorder(Protocol):
    """The duck type the extractor expects."""

    def record(self, record: LLMCallRecord) -> None: ...


class NoOpRecorder:
    """Recorder that drops every call."""

    def record(self, record: LLMCallRecord) -> None:  # noqa: D102 - protocol impl
        return None


class CallRecorder:
    """Collects calls in memory and forwards them to a repository."""

    def __init__(
        self,
        repository: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self.records: list[LLMCallRecord] = []

    def record(self, record: LLMCallRecord) -> None:
        """Store one call and forward it to the repository, if there is one."""
        self.records.append(record)
        repository = self.repository
        if repository is None:
            return
        store = getattr(repository, "record_llm_call", None)
        if store is None:
            return
        try:
            store(record)
        except Exception:  # pragma: no cover - the database must never break extraction
            logger.exception("could not store the llm call record")

    @property
    def total_cost(self) -> float:
        """Return the summed cost of every recorded call."""
        return sum(record.cost for record in self.records)

    @property
    def total_tokens_in(self) -> int:
        """Return the summed input tokens of every recorded call."""
        return sum(record.tokens_in for record in self.records)

    @property
    def total_tokens_out(self) -> int:
        """Return the summed output tokens of every recorded call."""
        return sum(record.tokens_out for record in self.records)


def estimate_cost(tokens_in: int, tokens_out: int, settings: Settings | None = None) -> float:
    """Return the USD cost of a call (NFR-05)."""
    settings = settings or get_settings()
    cost = (tokens_in / 1_000_000) * settings.llm_cost_per_million_input
    cost += (tokens_out / 1_000_000) * settings.llm_cost_per_million_output
    return cost


def usage_from_response(response: Any) -> tuple[int, int]:
    """Return ``(tokens_in, tokens_out)`` for a model response.

    The token counts come from the usage metadata of the response. A response
    without usage metadata (many test doubles, some providers) counts as zero.
    """
    if response is None:
        return 0, 0
    if isinstance(response, dict):
        response = response.get("raw") or response.get("parsed")
    usage = getattr(response, "usage_metadata", None)
    tokens_in = 0
    tokens_out = 0
    if isinstance(usage, dict):
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0)
    if not tokens_in and not tokens_out:
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, dict):
            legacy = metadata.get("token_usage") or metadata.get("usage")
            if isinstance(legacy, dict):
                tokens_in = int(legacy.get("prompt_tokens") or legacy.get("input_tokens") or 0)
                tokens_out = int(
                    legacy.get("completion_tokens") or legacy.get("output_tokens") or 0
                )
    return max(tokens_in, 0), max(tokens_out, 0)


def build_call_record(
    chain: str,
    model: str,
    response: Any = None,
    prompt_version: str = "",
    part_id: str | None = None,
    cached: bool = False,
    duration_ms: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    settings: Settings | None = None,
) -> LLMCallRecord:
    """Build the record of one LLM call."""
    settings = settings or get_settings()
    if tokens_in is None or tokens_out is None:
        used_in, used_out = usage_from_response(response)
        tokens_in = used_in if tokens_in is None else tokens_in
        tokens_out = used_out if tokens_out is None else tokens_out
    cost = estimate_cost(tokens_in, tokens_out, settings)
    return LLMCallRecord(
        chain=chain,
        model=model,
        tokens_in=int(tokens_in),
        tokens_out=int(tokens_out),
        cost=cost,
        prompt_version=prompt_version,
        part_id=part_id,
        cached=bool(cached),
        duration_ms=duration_ms,
    )


__all__ = [
    "CallRecorder",
    "LLMCallRecord",
    "NoOpRecorder",
    "Recorder",
    "build_call_record",
    "estimate_cost",
    "usage_from_response",
]
