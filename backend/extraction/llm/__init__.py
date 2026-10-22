"""PartPilot LLM extraction (plan WP4, tiers 2 and 3).

Public API::

    from extraction.llm import LLMExtractorImpl, build_chat_model, CallRecorder

    extractor = LLMExtractorImpl(recorder=CallRecorder())
    result = extractor.extract_tier2([(1, page_text)], Family.MOSFET, part_id="p1")

Nothing in this package opens a provider connection at import time.
"""

from __future__ import annotations

from .chains import (
    CHAIN_ALTERNATIVE,
    CHAIN_NAME_MAPPER,
    CHAIN_SEARCH_FILTER,
    CHAIN_TIER2,
    CHAIN_TIER3,
    ChainResult,
    NameMappingProposal,
)
from .extractor import LLMExtractorImpl
from .factory import build_chat_model, chat_model_core, setup_llm_cache
from .parameters import (
    ALL_PARAMETER_NAMES,
    GATE_DRIVER_PARAMETER_NAMES,
    MOSFET_PARAMETER_NAMES,
    is_known_parameter,
    parameter_names_for,
    spec_model_for,
)
from .prompt_store import (
    PROMPTS_DIR,
    available_versions,
    list_prompts,
    load_prompt,
    prompt_chain,
    prompt_version,
)
from .recorder import CallRecorder, NoOpRecorder, build_call_record, estimate_cost

__all__ = [
    "ALL_PARAMETER_NAMES",
    "CHAIN_ALTERNATIVE",
    "CHAIN_NAME_MAPPER",
    "CHAIN_SEARCH_FILTER",
    "CHAIN_TIER2",
    "CHAIN_TIER3",
    "CallRecorder",
    "ChainResult",
    "GATE_DRIVER_PARAMETER_NAMES",
    "LLMExtractorImpl",
    "MOSFET_PARAMETER_NAMES",
    "NameMappingProposal",
    "NoOpRecorder",
    "PROMPTS_DIR",
    "available_versions",
    "build_call_record",
    "build_chat_model",
    "chat_model_core",
    "estimate_cost",
    "is_known_parameter",
    "list_prompts",
    "load_prompt",
    "parameter_names_for",
    "prompt_chain",
    "prompt_version",
    "setup_llm_cache",
    "spec_model_for",
]
