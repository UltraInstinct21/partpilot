"""The repository has to satisfy the frozen ``PartsRepository`` protocol."""

from __future__ import annotations

import inspect

from db.repository import NameMapRepository, SqlAlchemyPartsRepository
from shared import interfaces


def test_the_repository_implements_every_protocol_method() -> None:
    for name in (
        "add_part",
        "get_part",
        "get_part_by_mpn",
        "list_parts",
        "get_parameters",
        "get_parameter",
        "update_parameter",
        "add_source",
        "get_source",
        "get_source_page",
        "add_offer",
        "list_review_queue",
        "apply_review",
        "record_llm_call",
        "stats",
    ):
        assert hasattr(SqlAlchemyPartsRepository, name), f"{name} is missing"
        assert callable(getattr(SqlAlchemyPartsRepository, name))


def test_the_signatures_match_the_protocol() -> None:
    protocol = interfaces.PartsRepository
    for name in protocol.__protocol_attrs__:
        expected = inspect.signature(getattr(protocol, name))
        actual = inspect.signature(getattr(SqlAlchemyPartsRepository, name))
        expected_params = list(expected.parameters)
        actual_params = list(actual.parameters)
        assert actual_params[: len(expected_params)] == expected_params, name
        for expected_param, actual_param in zip(expected_params, actual_params, strict=False):
            if expected_param == "self":
                continue
            assert (
                actual.parameters[actual_param].default
                == expected.parameters[expected_param].default
            ), name


def test_the_runtime_check_fails(repo) -> None:
    assert isinstance(repo, interfaces.PartsRepository)


def test_the_name_map_repository_has_its_api(name_map) -> None:
    for name in ("lookup", "add", "all_mappings", "set_approved"):
        assert hasattr(NameMapRepository, name), f"{name} is missing"
