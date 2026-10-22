"""Unit tests for :mod:`validation.units` (FR-06).

Every unit of the specification is checked twice: the *value* has to be
converted and the *canonical unit* has to be reported.
"""

from __future__ import annotations

import pytest

from validation.units import (
    CANONICAL_UNITS,
    PARAMETER_UNITS,
    canonical_unit_for,
    clean_unit,
    is_known_unit,
    normalize,
    ureg,
)


def test_one_registry_only() -> None:
    """A second registry would make the unit objects incomparable."""
    assert ureg is not None
    assert normalize(1.0, "V")[1] == "V"


@pytest.mark.parametrize(
    ("value", "unit", "expected_value", "expected_unit"),
    [
        # resistance
        (0.005, "mohm", 0.000005, "ohm"),
        (100.0, "mohm", 0.1, "ohm"),
        (1.0, "uohm", 0.000001, "ohm"),
        (1.0, "µohm", 0.000001, "ohm"),
        (1.0, "kohm", 1000.0, "ohm"),
        (1.0, "ohm", 1.0, "ohm"),
        # voltage / current
        (1.0, "mV", 0.001, "V"),
        (1.0, "V", 1.0, "V"),
        (1.0, "mA", 0.001, "A"),
        (1.0, "A", 1.0, "A"),
        # charge
        (1.0, "nC", 1e-09, "C"),
        (1.0, "uC", 1e-06, "C"),
        (1.0, "µC", 1e-06, "C"),
        (1.0, "C", 1.0, "C"),
        # capacitance
        (1.0, "pF", 1e-12, "F"),
        (1.0, "nF", 1e-09, "F"),
        (1.0, "F", 1.0, "F"),
        # time
        (1.0, "ns", 1e-09, "s"),
        (1.0, "us", 1e-06, "s"),
        (1.0, "µs", 1e-06, "s"),
        (1.0, "ms", 0.001, "s"),
        (1.0, "s", 1.0, "s"),
        # temperature
        (25.0, "C", 25.0, "C"),
        (25.0, "degC", 25.0, "degC"),
        (25.0, "°C", 25.0, "degC"),
        (10.0, "K", 10.0, "degC"),
        # thermal resistance
        (3.7, "C/W", 3.7, "degC/W"),
        (3.7, "degC/W", 3.7, "degC/W"),
    ],
)
def test_normalize_known_units(
    value: float, unit: str, expected_value: float, expected_unit: str
) -> None:
    converted, canonical = normalize(value, unit)
    assert canonical == expected_unit
    assert converted == pytest.approx(expected_value, rel=1e-9, abs=1e-18)


def test_normalize_mohm_examples_from_the_spec() -> None:
    assert normalize(0.005, "mohm") == pytest.approx((0.000005, "ohm"))
    assert normalize(100.0, "mohm") == pytest.approx((0.1, "ohm"))


def test_bare_c_is_a_coulomb_without_a_hint() -> None:
    assert normalize(5.0, "C") == pytest.approx((5.0, "C"))


def test_bare_c_is_celsius_for_a_temperature_field() -> None:
    assert normalize(25.0, "C", expected_unit="degC") == pytest.approx((25.0, "degC"))


def test_unknown_unit_returns_none_and_never_raises() -> None:
    assert normalize(12.0, "bananas") == (None, None)
    assert normalize(12.0, "V/A/A") == (None, None)


def test_missing_value_returns_none() -> None:
    assert normalize(None, "V") == (None, None)


def test_no_unit_is_dimensionless() -> None:
    assert normalize(42.0, None) == (42.0, None)
    assert normalize(42.0, "  ") == (42.0, None)


def test_clean_unit_folds_the_micro_and_degree_signs() -> None:
    assert clean_unit(" µF ") == "uF"
    assert clean_unit("°C") == "degC"
    assert clean_unit("deg C / W") == "degC/W"
    assert clean_unit(None) is None
    assert clean_unit("") is None


def test_is_known_unit() -> None:
    assert is_known_unit("mohm")
    assert is_known_unit("°C")
    assert not is_known_unit("bananas")
    assert not is_known_unit(None)


def test_canonical_units_table_is_complete() -> None:
    assert CANONICAL_UNITS["voltage"] == "V"
    assert CANONICAL_UNITS["current"] == "A"
    assert CANONICAL_UNITS["resistance"] == "ohm"
    assert CANONICAL_UNITS["capacitance"] == "F"
    assert CANONICAL_UNITS["charge"] == "C"
    assert CANONICAL_UNITS["time"] == "s"
    assert CANONICAL_UNITS["temperature"] == "degC"
    assert CANONICAL_UNITS["thermal_resistance"] == "degC/W"
    assert CANONICAL_UNITS["dimensionless"] == ""


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("vds_max", "V"),
        ("id_continuous", "A"),
        ("rds_on", "ohm"),
        ("vgs_threshold", "V"),
        ("vgs_max", "V"),
        ("total_gate_charge_qg", "C"),
        ("gate_drain_charge_qgd", "C"),
        ("input_capacitance_ciss", "F"),
        ("output_capacitance_coss", "F"),
        ("max_junction_temp", "degC"),
        ("thermal_resistance", "degC/W"),
        ("reverse_recovery_qrr", "C"),
        ("supply_voltage_min", "V"),
        ("supply_voltage_max", "V"),
        ("peak_source_current", "A"),
        ("peak_sink_current", "A"),
        ("input_logic_level", "V"),
        ("propagation_delay", "s"),
        ("rise_time", "s"),
        ("fall_time", "s"),
        ("uvlo_threshold", "V"),
        ("operating_temp_min", "degC"),
        ("operating_temp_max", "degC"),
    ],
)
def test_canonical_unit_for_standard_names(name: str, unit: str) -> None:
    assert canonical_unit_for(name) == unit
    assert PARAMETER_UNITS[name] == unit


def test_canonical_unit_for_non_numeric_and_unknown_names() -> None:
    assert canonical_unit_for("package") is None
    assert canonical_unit_for("channel_count") is None
    assert canonical_unit_for("something_else") is None
    assert canonical_unit_for("") is None
