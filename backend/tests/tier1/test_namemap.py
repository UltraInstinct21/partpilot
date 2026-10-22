"""Tests of the symbol / label -> standard name matcher."""

from __future__ import annotations

import pytest

from extraction.tier1.namemap import (
    FAMILY_FIELDS,
    STANDARD_NAMES,
    NameMap,
    match_name,
    normalise_label,
    normalise_symbol,
)
from shared.schemas import Family


@pytest.mark.parametrize(
    ("label", "symbol", "expected"),
    [
        ("Drain-Source Voltage", "VDS", "vds_max"),
        ("Continuous Drain Current", "ID", "id_continuous"),
        ("Maximum Junction Temperature", "TJ", "max_junction_temp"),
        ("Drain-Source On-Resistance", "RDS(on)", "rds_on"),
        ("Gate-Source Threshold Voltage", "VGS(th)", "vgs_threshold"),
        ("Gate-Source Voltage", "VGS", "vgs_max"),
        ("Total Gate Charge", "QG", "total_gate_charge_qg"),
        ("Gate-Drain Charge", "QGD", "gate_drain_charge_qgd"),
        ("Input Capacitance", "CISS", "input_capacitance_ciss"),
        ("Output Capacitance", "COSS", "output_capacitance_coss"),
        ("Thermal Resistance, Junction-to-Case", "RthJC", "thermal_resistance"),
        ("Reverse Recovery Charge", "Qrr", "reverse_recovery_qrr"),
    ],
)
def test_mosfet_rows_match(label: str, symbol: str, expected: str) -> None:
    match = match_name(label, symbol=symbol, family=Family.MOSFET)
    assert match is not None
    assert match.names == (expected,)
    assert match.matched_by in {"symbol", "label"}


@pytest.mark.parametrize(
    ("label", "symbol", "expected"),
    [
        ("Peak Source Current", "IO+", "peak_source_current"),
        ("Peak Sink Current", "IO-", "peak_sink_current"),
        ("Input Low Level Voltage", "VIL", "input_logic_level"),
        ("Propagation Delay", "tPD", "propagation_delay"),
        ("Rise Time", "tR", "rise_time"),
        ("Fall Time", "tF", "fall_time"),
        ("UVLO Threshold", "UVLO", "uvlo_threshold"),
    ],
)
def test_gate_driver_rows_match(label: str, symbol: str, expected: str) -> None:
    match = match_name(label, symbol=symbol, family=Family.GATE_DRIVER)
    assert match is not None
    assert match.names == (expected,)


def test_compound_rows_return_two_names() -> None:
    supply = match_name("Supply Voltage", symbol="VCC", family=Family.GATE_DRIVER)
    assert supply is not None
    assert supply.names == ("supply_voltage_min", "supply_voltage_max")

    temperature = match_name("Operating Temperature", symbol="TOPR", family=Family.GATE_DRIVER)
    assert temperature is not None
    assert temperature.names == ("operating_temp_min", "operating_temp_max")


@pytest.mark.parametrize(
    "label",
    [
        "Total Doom Resistance",
        "Snog Values",
        "Quantum Entanglement Factor",
        "Comment",
    ],
)
def test_unknown_label_returns_none(label: str) -> None:
    assert match_name(label, family=Family.MOSFET) is None


def test_unknown_symbol_is_not_guessed() -> None:
    assert match_name("Some Parameter", symbol="XYZ9", family=Family.MOSFET) is None


def test_a_mosfet_name_is_not_used_for_a_gate_driver() -> None:
    # "VDS" is a MOSFET symbol; a gate driver row must not produce it
    assert match_name("Drain-Source Voltage", symbol="VDS", family=Family.GATE_DRIVER) is None


def test_injected_lookup_wins() -> None:
    def lookup(raw_name: str) -> str | None:
        return {"XYZ9": "rds_on"}.get(raw_name)

    name_map = NameMap(lookup)
    match = name_map.match("Some Parameter", symbol="XYZ9", family=Family.MOSFET)
    assert match is not None
    assert match.names == ("rds_on",)
    assert match.matched_by == "injected"


def test_injected_lookup_may_return_none() -> None:
    def lookup(raw_name: str) -> str | None:
        return None

    name_map = NameMap(lookup)
    assert name_map.match("Total Doom Resistance", family=Family.MOSFET) is None


def test_fuzzy_fallback_matches_a_near_miss_with_a_lower_confidence() -> None:
    match = match_name("Drain Source On Resistanc", family=Family.MOSFET)
    assert match is not None
    assert match.names == ("rds_on",)
    assert match.matched_by == "fuzzy"
    assert match.confidence < 0.85


def test_fuzzy_fallback_needs_a_high_score() -> None:
    assert match_name("Wibble wobble", family=Family.MOSFET) is None
    assert match_name("Total Doom Resistance", family=Family.MOSFET) is None


def test_normalisers() -> None:
    assert normalise_symbol("RDS(on)") == "RDS(ON)"
    assert normalise_symbol(" IO+ ") == "IO+"
    assert normalise_label("Thermal Resistance, Junction-to-Case") == (
        "THERMAL RESISTANCE JUNCTION TO CASE"
    )


def test_standard_names_cover_both_families() -> None:
    assert "rds_on" in STANDARD_NAMES
    assert "supply_voltage_min" in STANDARD_NAMES
    assert set(FAMILY_FIELDS[Family.MOSFET]) | set(FAMILY_FIELDS[Family.GATE_DRIVER]) == set(
        STANDARD_NAMES
    )
