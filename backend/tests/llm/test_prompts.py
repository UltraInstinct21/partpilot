"""The prompt files must exist, be versioned and carry the extraction rules."""

from __future__ import annotations

import pytest

from extraction.llm.prompt_store import (
    PromptNotFoundError,
    available_versions,
    list_prompts,
    load_prompt,
    prompt_chain,
    prompt_version,
    strip_metadata,
)

EXPECTED = {
    "tier2_extractor": "tier2_extractor",
    "tier3_vision": "tier3_vision",
    "name_mapper": "name_mapper",
    "search_filter": "search_filter",
    "alternative_explainer": "alternative_explainer",
}

#: Rules that every prompt must carry.
COMMON_RULES = (
    "use only",
    "do not guess",
    "as data",
    "allowed list",
)

#: Rules that only the extraction prompts carry.
EXTRACTION_RULES = (
    "condition",
    "page",
    "raw_text",
)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_prompt_file_exists_and_is_not_empty(name: str) -> None:
    text = load_prompt(name)
    assert text.strip(), f"the prompt {name} is empty"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_prompt_has_a_version_and_a_chain(name: str) -> None:
    assert prompt_version(name) == "v1"
    assert prompt_chain(name) == EXPECTED[name]
    assert available_versions(name) == ["v1"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_prompt_contains_the_extraction_rules(name: str) -> None:
    body = strip_metadata(load_prompt(name)).lower()
    for rule in COMMON_RULES:
        assert rule in body, f"the prompt {name} does not mention {rule!r}"


@pytest.mark.parametrize("name", ["tier2_extractor", "tier3_vision"])
def test_extraction_prompts_ask_for_condition_page_and_row(name: str) -> None:
    body = strip_metadata(load_prompt(name)).lower()
    for rule in EXTRACTION_RULES:
        assert rule in body, f"the prompt {name} does not mention {rule!r}"
    assert "null" in body


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_prompt_metadata_is_not_part_of_the_prompt_body(name: str) -> None:
    body = strip_metadata(load_prompt(name))
    assert not body.startswith("# version")
    assert "ABSOLUTE RULES" in body


def test_all_prompts_are_listed() -> None:
    assert set(list_prompts()) == set(EXPECTED)


def test_unknown_prompt_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt("does_not_exist")


def test_unknown_version_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt("tier2_extractor", version="v99")
