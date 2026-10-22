"""The five LLM chains of PartPilot (plan WP4).

| chain | input | output |
| --- | --- | --- |
| ``tier2_extractor`` | page text and table data | values, conditions, page numbers |
| ``tier3_vision`` | rendered page image | the same |
| ``name_mapper`` | unknown parameter name | a proposed standard name |
| ``search_filter`` | user query | a filter object |
| ``alternative_explainer`` | two parts and their differences | one short sentence |

The chains are fixed and deterministic: no agent, no tool loop, no free
interpretation. Every chain uses one prompt file (with a version) and, where a
structured result is needed, one Pydantic schema from ``shared.schemas``.

NFR-03 is enforced in three places:

* the prompt forbids guessing,
* a field the model did not fill in becomes a **failed field** and is never
  replaced by a default,
* the alternative explainer is checked for numbers that are not in its input
  and is replaced by a deterministic sentence when it fails that check.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from shared.schemas import (
    ExtractionMethod,
    Family,
    GateDriverSpec,
    MosfetSpec,
    ParameterValue,
    SearchFilter,
    SpecValue,
)

from .factory import chat_model_core, retry_attempts
from .parameters import (
    describe_spec_schema,
    is_known_parameter,
    parameter_names_for,
    spec_model_for,
    unit_hint,
)
from .prompt_store import (
    load_prompt,
    prompt_chain,
    prompt_version,
    strip_metadata,
)

logger = logging.getLogger(__name__)

CHAIN_TIER2 = "tier2_extractor"
CHAIN_TIER3 = "tier3_vision"
CHAIN_NAME_MAPPER = "name_mapper"
CHAIN_SEARCH_FILTER = "search_filter"
CHAIN_ALTERNATIVE = "alternative_explainer"

PROMPT_TIER2 = "tier2_extractor"
PROMPT_TIER3 = "tier3_vision"
PROMPT_NAME_MAPPER = "name_mapper"
PROMPT_SEARCH_FILTER = "search_filter"
PROMPT_ALTERNATIVE = "alternative_explainer"

#: Confidence base per tier (contract section "Confidence model").
TIER_CONFIDENCE = {
    ExtractionMethod.TIER2: 0.75,
    ExtractionMethod.TIER3: 0.70,
}

MAX_EXPLANATION_WORDS = 25
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


class NameMappingProposal(BaseModel):
    """The output of the name mapper chain.

    The proposal is **never** an approval: a person has to accept it before it
    is stored in the ``name_map`` table.
    """

    model_config = ConfigDict(extra="ignore")

    standard_name: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


@dataclass
class ChainResult:
    """The outcome of one chain call."""

    value: Any = None
    raw: Any = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: int = 0
    prompt_version: str = ""
    model: str = ""


# --------------------------------------------------------------------------------------
# Model helpers
# --------------------------------------------------------------------------------------


def model_name(model: Any) -> str:
    """Return a printable name of the model (used in ``llm_calls.model``)."""
    core = chat_model_core(model)
    for candidate in (core, model):
        if candidate is None:
            continue
        for attribute in ("model_name", "model", "model_id", "deployment_name"):
            value = getattr(candidate, attribute, None)
            if isinstance(value, str) and value:
                return value
    return type(model).__name__


def structured_runner(model: Any, schema: type[BaseModel]) -> Any:
    """Return a runnable that produces ``schema`` objects.

    ``include_raw=True`` keeps the raw message, which is where the token usage
    metadata lives.
    """
    core = chat_model_core(model)
    if core is None:
        raise TypeError("the model does not support structured output")
    runner = core.with_structured_output(schema, include_raw=True)
    attempts = retry_attempts(model)
    if attempts:
        runner = runner.with_retry(stop_after_attempt=attempts)
    return runner


def _usage(response: Any) -> tuple[int, int]:
    from .recorder import usage_from_response

    return usage_from_response(response)


# --------------------------------------------------------------------------------------
# Prompt payloads
# --------------------------------------------------------------------------------------


def _allowed_names(family: Family) -> str:
    return ", ".join(parameter_names_for(family))


def _table_rows(text: str) -> list[str]:
    """Return the lines of ``text`` that look like a table row."""
    rows = [line.strip() for line in text.splitlines() if "|" in line]
    return rows


def build_tier2_payload(family: Family, pages: Sequence[tuple[int, str]]) -> str:
    """Build the user message of the tier 2 chain.

    Only the pages that were handed over are used - never the whole PDF.
    """
    model = spec_model_for(family)
    parts = [
        f"FAMILY: {family.value}",
        f"ALLOWED PARAMETER NAMES: {_allowed_names(family)}",
        "",
        describe_spec_schema(model),
        "",
        "PAGES (this is the only material you may use):",
    ]
    for number, text in pages:
        parts.append("")
        parts.append(f"BEGIN PAGE {number}")
        parts.append(text.strip())
        rows = _table_rows(text)
        if rows:
            parts.append(f"TABLE ROWS ON PAGE {number}:")
            parts.extend(rows)
        parts.append(f"END PAGE {number}")
    parts.append("")
    parts.append("Extract every slot you can read on the pages above. Use null otherwise.")
    return "\n".join(parts)


def build_tier3_payload(family: Family, page: int) -> str:
    """Build the user message of the tier 3 chain (one rendered page)."""
    model = spec_model_for(family)
    return "\n".join(
        [
            f"FAMILY: {family.value}",
            f"ALLOWED PARAMETER NAMES: {_allowed_names(family)}",
            "",
            describe_spec_schema(model),
            "",
            f"PAGE IMAGE: page {page} of the datasheet is attached to this message.",
            "Extract every slot you can read in the image. Use null otherwise.",
        ]
    )


def build_name_mapper_payload(raw_name: str, family: Family) -> str:
    """Build the user message of the name mapper chain."""
    return "\n".join(
        [
            f"FAMILY: {family.value}",
            f"ALLOWED PARAMETER NAMES: {_allowed_names(family)}",
            "",
            "UNIT HINTS:",
            *[f"  - {name}: {unit_hint(name)}" for name in parameter_names_for(family)],
            "",
            f'RAW NAME: "{raw_name}"',
            "",
            "Propose the standard name, or null when it is unclear.",
        ]
    )


def build_search_filter_payload(query: str) -> str:
    """Build the user message of the search filter chain."""
    from .parameters import ALL_PARAMETER_NAMES

    return "\n".join(
        [
            "ALLOWED FAMILIES: mosfet, gate_driver",
            f"ALLOWED PARAMETER NAMES: {', '.join(ALL_PARAMETER_NAMES)}",
            "",
            f"USER QUESTION: {query}",
            "",
            "Build the filter that expresses this question.",
        ]
    )


def build_alternative_payload(differences: dict[str, dict[str, float | None]], mpn: str) -> str:
    """Build the user message of the alternative explainer chain."""
    from .parameters import ALL_PARAMETER_NAMES

    return "\n".join(
        [
            f"ALLOWED PARAMETER NAMES: {', '.join(ALL_PARAMETER_NAMES)}",
            "",
            f"PART: {mpn}",
            "DIFFERENCES (JSON, the first key is the reference part):",
            json.dumps(differences, indent=2, sort_keys=True, default=str),
            "",
            "Write one sentence about the trade-off.",
        ]
    )


# --------------------------------------------------------------------------------------
# Message builders
# --------------------------------------------------------------------------------------


def _system_message(prompt_name: str, directory: Any = None) -> SystemMessage:
    rules = strip_metadata(load_prompt(prompt_name, directory=directory))
    return SystemMessage(content=rules)


def build_tier2_messages(
    family: Family, pages: Sequence[tuple[int, str]], directory: Any = None
) -> list[BaseMessage]:
    """Return the messages of the tier 2 chain."""
    return [
        _system_message(PROMPT_TIER2, directory),
        HumanMessage(content=build_tier2_payload(family, pages)),
    ]


def build_tier3_messages(
    family: Family, page: int, image: bytes, directory: Any = None
) -> list[BaseMessage]:
    """Return the messages of the tier 3 chain (text plus the page image)."""
    encoded = base64.b64encode(image).decode("ascii")
    content: list[dict[str, Any]] = [{"type": "text", "text": build_tier3_payload(family, page)}]
    if image:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            }
        )
    return [
        _system_message(PROMPT_TIER3, directory),
        HumanMessage(content=content),
    ]


def build_name_mapper_messages(
    raw_name: str, family: Family, directory: Any = None
) -> list[BaseMessage]:
    """Return the messages of the name mapper chain."""
    return [
        _system_message(PROMPT_NAME_MAPPER, directory),
        HumanMessage(content=build_name_mapper_payload(raw_name, family)),
    ]


def build_search_filter_messages(query: str, directory: Any = None) -> list[BaseMessage]:
    """Return the messages of the search filter chain."""
    return [
        _system_message(PROMPT_SEARCH_FILTER, directory),
        HumanMessage(content=build_search_filter_payload(query)),
    ]


def build_alternative_messages(
    differences: dict[str, dict[str, float | None]], mpn: str, directory: Any = None
) -> list[BaseMessage]:
    """Return the messages of the alternative explainer chain."""
    return [
        _system_message(PROMPT_ALTERNATIVE, directory),
        HumanMessage(content=build_alternative_payload(differences, mpn)),
    ]


# --------------------------------------------------------------------------------------
# Result handling
# --------------------------------------------------------------------------------------


def spec_to_values(
    spec: MosfetSpec | GateDriverSpec,
    method: ExtractionMethod,
    part_id: str | None = None,
) -> tuple[list[ParameterValue], list[str]]:
    """Turn a spec object into values plus the list of failed fields.

    A field the model did not fill in is a **failed field** (NFR-03). It is
    never replaced by a default value.
    """
    values: list[ParameterValue] = []
    failed: list[str] = []
    base_confidence = TIER_CONFIDENCE.get(method, 0.70)
    for name, slot in spec.model_dump().items():
        if slot is None:
            failed.append(name)
            continue
        spec_value = SpecValue.model_validate(slot)
        if spec_value.value is None:
            failed.append(name)
            continue
        confidence = spec_value.confidence if spec_value.confidence > 0 else base_confidence
        values.append(
            ParameterValue(
                part_id=part_id,
                name=name,
                value=spec_value.value,
                unit=spec_value.unit,
                condition=dict(spec_value.condition or {}),
                source_id=spec_value.source_id,
                page=spec_value.page,
                method=method,
                confidence=min(max(confidence, 0.0), 1.0),
                raw_text=spec_value.raw_text,
            )
        )
    return values, failed


def merge_specs(
    specs: Iterable[MosfetSpec | GateDriverSpec],
) -> tuple[MosfetSpec | GateDriverSpec | None, list[str]]:
    """Merge the specs of several pages into one.

    The first spec that carries a value for a slot wins; the slots that no page
    carried are the failed fields.
    """
    merged: dict[str, Any] = {}
    failed: list[str] = []
    model: type[BaseModel] | None = None
    for spec in specs:
        model = type(spec)
        for name, slot in spec.model_dump().items():
            if slot is None:
                continue
            if merged.get(name) is None:
                merged[name] = slot
    if model is None:
        return None, failed
    for name in model.model_fields:
        if merged.get(name) is None:
            failed.append(name)
    return model.model_validate(merged), failed


def _numbers_in(text: str) -> set[float]:
    """Return every number that occurs in ``text``."""
    found: set[float] = set()
    for match in _NUMBER_RE.finditer(text or ""):
        try:
            found.add(float(match.group(0)))
        except ValueError:  # pragma: no cover - the regex only matches numbers
            continue
    return found


def clean_explanation(
    sentence: str, differences: dict[str, dict[str, float | None]], mpn: str
) -> str:
    """Return a sentence that is short and that invents no number.

    The sentence of the model is accepted when it is at most
    :data:`MAX_EXPLANATION_WORDS` words long and when every number in it also
    occurs in the input. Otherwise a deterministic sentence is used.
    """
    candidate = (sentence or "").strip().strip('"').strip()
    if candidate:
        candidate = candidate.splitlines()[0].strip()
        parts = re.split(r"(?<=[.!?])\s+", candidate)
        if len(parts) > 1:
            candidate = parts[0].strip()
        if candidate and not candidate.endswith((".", "!", "?")):
            candidate += "."
    allowed = _numbers_in(json.dumps(differences, default=str)) | _numbers_in(mpn)
    used = _numbers_in(candidate)
    if candidate and len(candidate.split()) <= MAX_EXPLANATION_WORDS and used <= allowed:
        return candidate
    if candidate and len(candidate.split()) > MAX_EXPLANATION_WORDS:
        logger.info("alternative explanation was too long, using the deterministic one")
    return fallback_explanation(differences, mpn)


def fallback_explanation(differences: dict[str, dict[str, float | None]], mpn: str) -> str:
    """Build the trade-off sentence from the differences, without the model."""
    parts: list[str] = []
    for name, values in differences.items():
        items = [(key, value) for key, value in values.items() if value is not None]
        if len(items) < 2:
            continue
        (_, first), (_, second) = items[0], items[1]
        if second == first:
            parts.append(f"the same {name}")
        elif second < first:
            parts.append(f"lower {name}")
        else:
            parts.append(f"higher {name}")
    if not parts:
        return f"{mpn} shows no measurable difference on the compared parameters."
    sentence = f"{mpn} has " + " but ".join(parts) + " than the reference part."
    words = sentence.split()
    if len(words) > MAX_EXPLANATION_WORDS:
        sentence = " ".join(words[:MAX_EXPLANATION_WORDS]).rstrip(",") + "."
    return sentence


def validate_search_filter(filt: SearchFilter) -> SearchFilter:
    """Drop every constraint with a parameter name outside the allowed set.

    The LLM only builds the filter, the database executes it. A constraint on a
    name that does not exist is dropped and logged.
    """
    kept = []
    for constraint in filt.parameters:
        if is_known_parameter(constraint.name):
            kept.append(constraint)
            continue
        logger.warning("dropping filter constraint on unknown parameter %r", constraint.name)
    filt.parameters = kept
    return filt


# --------------------------------------------------------------------------------------
# Chain calls
# --------------------------------------------------------------------------------------


def call_structured(
    model: Any,
    schema: type[BaseModel],
    messages: list[BaseMessage],
    prompt_name: str,
    directory: Any = None,
) -> ChainResult:
    """Run a chain that returns a structured object."""
    started = time.perf_counter()
    runner = structured_runner(model, schema)
    response = runner.invoke(messages)
    duration_ms = int((time.perf_counter() - started) * 1000)
    raw = response.get("raw") if isinstance(response, dict) else response
    parsed = response.get("parsed") if isinstance(response, dict) else response
    error = response.get("parsing_error") if isinstance(response, dict) else None
    tokens_in, tokens_out = _usage(raw)
    return ChainResult(
        value=parsed,
        raw=raw,
        error=str(error) if error is not None else None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        duration_ms=duration_ms,
        prompt_version=prompt_version(prompt_name, directory=directory),
        model=model_name(model),
    )


def call_text(
    model: Any,
    messages: list[BaseMessage],
    prompt_name: str,
    directory: Any = None,
) -> ChainResult:
    """Run a chain that returns plain text."""
    started = time.perf_counter()
    response = model.invoke(messages)
    duration_ms = int((time.perf_counter() - started) * 1000)
    content = ""
    if isinstance(response, AIMessage):
        content = response.content if isinstance(response.content, str) else str(response.content)
    elif isinstance(response, str):
        content = response
    tokens_in, tokens_out = _usage(response)
    return ChainResult(
        value=content,
        raw=response,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        duration_ms=duration_ms,
        prompt_version=prompt_version(prompt_name, directory=directory),
        model=model_name(model),
    )


def chain_names() -> list[str]:
    """Return the names of the five chains."""
    return [
        CHAIN_TIER2,
        CHAIN_TIER3,
        CHAIN_NAME_MAPPER,
        CHAIN_SEARCH_FILTER,
        CHAIN_ALTERNATIVE,
    ]


def prompt_chain_names() -> dict[str, str]:
    """Return the chain name that every prompt file declares."""
    return {
        name: prompt_chain(name)
        for name in (
            PROMPT_TIER2,
            PROMPT_TIER3,
            PROMPT_NAME_MAPPER,
            PROMPT_SEARCH_FILTER,
            PROMPT_ALTERNATIVE,
        )
    }


__all__ = [
    "CHAIN_ALTERNATIVE",
    "CHAIN_NAME_MAPPER",
    "CHAIN_SEARCH_FILTER",
    "CHAIN_TIER2",
    "CHAIN_TIER3",
    "ChainResult",
    "NameMappingProposal",
    "build_alternative_messages",
    "build_name_mapper_messages",
    "build_search_filter_messages",
    "build_tier2_messages",
    "build_tier2_payload",
    "build_tier3_messages",
    "build_tier3_payload",
    "call_structured",
    "call_text",
    "chain_names",
    "clean_explanation",
    "fallback_explanation",
    "merge_specs",
    "model_name",
    "prompt_chain_names",
    "spec_to_values",
    "structured_runner",
    "validate_search_filter",
]
