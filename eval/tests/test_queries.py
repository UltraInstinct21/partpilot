"""Tests for the 30 natural-language search queries."""

from __future__ import annotations

from eval.queries import EXPECTED_FILTER_KEYS, QUERIES, QUERY_COUNT, validate_queries


def test_the_query_list_holds_thirty_queries() -> None:
    assert len(QUERIES) == QUERY_COUNT == 30


def test_the_query_list_is_valid() -> None:
    assert validate_queries() == []


def test_every_query_has_a_text_and_an_expected_filter() -> None:
    for query, expected in QUERIES:
        assert query.strip()
        assert isinstance(expected, dict)
        assert expected


def test_the_expected_filters_use_only_search_filter_fields() -> None:
    for _query, expected in QUERIES:
        for key in expected:
            assert key in EXPECTED_FILTER_KEYS


def test_the_validator_reports_a_duplicate_query() -> None:
    problems = validate_queries([("q", {"family": "mosfet"}), ("q", {"family": "mosfet"})])
    assert any("used twice" in problem for problem in problems)


def test_the_validator_reports_an_unknown_filter_key() -> None:
    problems = validate_queries([("q", {"colour": "red"})])
    assert any("is not a SearchFilter field" in problem for problem in problems)


def test_the_validator_reports_a_constraint_without_a_bound() -> None:
    problems = validate_queries([("q", {"parameters": [{"name": "rds_on"}]})])
    assert any("no min, max or typ" in problem for problem in problems)


def test_the_validator_reports_a_constraint_without_a_name() -> None:
    problems = validate_queries([("q", {"parameters": [{"max": 5.0}]})])
    assert any("no name" in problem for problem in problems)
