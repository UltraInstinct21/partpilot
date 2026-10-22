"""Tests of the fuzzy name matcher."""

from __future__ import annotations

import pytest

from validation.namemap import DEFAULT_ALIASES, NameMatcher, normalize_name


@pytest.fixture()
def matcher() -> NameMatcher:
    return NameMatcher()


def test_normalize_name() -> None:
    assert normalize_name("Rds(on)") == "rds on"
    assert normalize_name("RDS (ON)") == "rds on"
    assert normalize_name("  V_DS  ") == "v ds"
    assert normalize_name(None) == ""


def test_exact_match_on_a_known_alias(matcher: NameMatcher) -> None:
    name, score = matcher.match_with_score("Vds")
    assert name == "vds_max"
    assert score == 1.0


def test_exact_match_on_a_standard_name(matcher: NameMatcher) -> None:
    assert matcher.match("total_gate_charge_qg") == "total_gate_charge_qg"
    assert matcher.match("Rds(on)") == "rds_on"
    assert matcher.match("Qg") == "total_gate_charge_qg"


def test_fuzzy_match_above_the_threshold(matcher: NameMatcher) -> None:
    name, score = matcher.match_with_score("Drain Source Voltage Rating")
    assert name == "vds_max"
    assert score >= matcher.threshold
    # a fuzzy match is not an exact match
    assert score != 1.0


def test_match_below_the_threshold_returns_none(matcher: NameMatcher) -> None:
    name, score = matcher.match_with_score("banana")
    assert name is None
    assert score < matcher.threshold


def test_ambiguous_match_returns_none(matcher: NameMatcher) -> None:
    """ "operating temperature" fits the min field and the max field."""
    name, score = matcher.match_with_score("operating temperature")
    assert name is None
    assert score >= matcher.threshold


def test_ambiguity_can_be_resolved_by_a_better_alias(matcher: NameMatcher) -> None:
    assert matcher.match("operating temperature min") == "operating_temp_min"
    assert matcher.match("operating temperature max") == "operating_temp_max"


def test_an_injected_mapping_is_used() -> None:
    matcher = NameMatcher({"my own label": "vds_max"})
    assert matcher.match("my own label") == "vds_max"
    assert matcher.match("Vds") == "vds_max"


def test_an_injected_callable_is_used() -> None:
    def lookup(raw_name: str) -> str | None:
        return "vds_max" if raw_name.startswith("my") else None

    matcher = NameMatcher(lookup)
    assert matcher.match("my special label") == "vds_max"
    assert matcher.match_with_score("my special label")[1] == 1.0


def test_a_broken_lookup_never_raises() -> None:
    def lookup(raw_name: str) -> str | None:
        raise RuntimeError("the database is gone")

    matcher = NameMatcher(lookup)
    assert matcher.match("Vds") == "vds_max"


def test_extra_aliases_can_be_added() -> None:
    matcher = NameMatcher()
    matcher.add_alias("gate charge total", "total_gate_charge_qg")
    assert matcher.match("gate charge total") == "total_gate_charge_qg"


def test_candidates_are_ranked(matcher: NameMatcher) -> None:
    candidates = matcher.candidates("gate charge", limit=3)
    assert candidates
    assert candidates == sorted(candidates, key=lambda item: -item[1])
    assert candidates[0][0] == "total_gate_charge_qg"


def test_standard_names_are_known(matcher: NameMatcher) -> None:
    names = matcher.standard_names()
    assert "vds_max" in names
    assert "package" in names
    assert len(names) == len(set(names))


def test_empty_input_returns_nothing(matcher: NameMatcher) -> None:
    assert matcher.match("") is None
    assert matcher.match(None) is None
    assert matcher.candidates("") == []


def test_the_default_alias_table_covers_every_mosfet_and_driver_field() -> None:
    targets = set(DEFAULT_ALIASES.values())
    for name in (
        "vds_max",
        "id_continuous",
        "rds_on",
        "vgs_threshold",
        "vgs_max",
        "total_gate_charge_qg",
        "gate_drain_charge_qgd",
        "input_capacitance_ciss",
        "output_capacitance_coss",
        "max_junction_temp",
        "thermal_resistance",
        "reverse_recovery_qrr",
        "supply_voltage_min",
        "supply_voltage_max",
        "peak_source_current",
        "peak_sink_current",
        "input_logic_level",
        "propagation_delay",
        "rise_time",
        "fall_time",
        "uvlo_threshold",
        "channel_count",
        "operating_temp_min",
        "operating_temp_max",
    ):
        assert name in targets, f"{name} has no alias"
