"""Tests of the vendor label -> standard name mapping."""

from __future__ import annotations

import pytest

from collectors.params import (
    canonical_unit,
    infer_family,
    parse_condition,
    parse_value_with_unit,
    resolve_parameter_name,
    slugify,
)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Drain to Source Voltage (Vdss)", "vds_max"),
        ("Drain Source Voltage (Vdss)", "vds_max"),
        ("Continuous Drain Current (Id) @ 25°C", "id_continuous"),
        ("RDS(on) @ Id, Vgs", "rds_on"),
        ("Gate Threshold Voltage (Vgs(th))", "vgs_threshold"),
        ("Total Gate Charge (Qg)", "total_gate_charge_qg"),
        ("Package / Case", "package"),
        ("Gate-Drain Charge (Qgd)", "gate_drain_charge_qgd"),
        ("Input Capacitance (Ciss)", "input_capacitance_ciss"),
        ("Output Capacitance (Coss)", "output_capacitance_coss"),
        ("Thermal Resistance - Junction to Case (RthJC)", "thermal_resistance"),
        ("Reverse Recovery Charge (Qrr)", "reverse_recovery_qrr"),
        ("Peak Source Current", "peak_source_current"),
        ("Propagation Delay Time", "propagation_delay"),
        ("Undervoltage Lockout Threshold", "uvlo_threshold"),
        ("Number of Channels", "channel_count"),
    ],
)
def test_a_known_label_is_mapped(label: str, expected: str) -> None:
    assert resolve_parameter_name(label) == expected


def test_an_unknown_label_is_never_guessed() -> None:
    assert resolve_parameter_name("Watts of Pure Spunk") is None
    assert resolve_parameter_name("") is None
    assert resolve_parameter_name(None) is None


def test_the_fuzzy_match_is_off_by_default_and_never_guesses() -> None:
    assert resolve_parameter_name("Drain to Source Voltage") is None
    assert resolve_parameter_name("Drain to Source Voltage", allow_fuzzy=True) == "vds_max"
    assert resolve_parameter_name("Watts of Pure Spunk", allow_fuzzy=True) is None


def test_the_short_name_of_a_nexar_attribute_is_mapped() -> None:
    assert resolve_parameter_name("vds") == "vds_max"
    assert resolve_parameter_name("qg") == "total_gate_charge_qg"
    assert resolve_parameter_name("ciss") == "input_capacitance_ciss"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("56.0 V", (56.0, "V")),
        ("12.0 mOhm", (12.0, "mohm")),
        ("3.2 A", (3.2, "A")),
        ("37.5 nC", (37.5, "nC")),
        ("4900 pF", (4900.0, "pF")),
        ("TO-220AB", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_a_value_is_split_into_a_number_and_a_unit(
    text: str | None, expected: tuple[float | None, str | None]
) -> None:
    assert parse_value_with_unit(text) == expected


def test_the_unit_is_canonicalised() -> None:
    assert canonical_unit("mOhm") == "mohm"
    assert canonical_unit("nC") == "nC"
    assert canonical_unit("°C") == "degC"
    assert canonical_unit("parsec") is None
    assert canonical_unit(None) is None


def test_the_condition_travels_with_the_value() -> None:
    assert parse_condition("Continuous Drain Current (Id) @ 25°C") == {"Tc": "25 C"}
    assert parse_condition("RDS(on) @ Id, Vgs") == {"Id": "specified", "Vgs": "specified"}
    assert parse_condition("Package / Case") == {}
    assert parse_condition(None) == {}


def test_the_family_is_guessed_from_the_text() -> None:
    assert infer_family("Transistors - FETs, MOSFETs") == "mosfet"
    assert infer_family("PMIC - Gate Drivers") == "gate_driver"
    assert infer_family("N-channel power MOSFET, 56 V") == "mosfet"
    assert infer_family("high-side gate driver, 25 V") == "gate_driver"
    assert infer_family("something else") is None


def test_the_slug_is_stable() -> None:
    assert slugify("IRF3205S") == "irf3205s"
    assert slugify("DMN3024U-13") == "dmn3024u-13"
    assert slugify("  ") == "part"
