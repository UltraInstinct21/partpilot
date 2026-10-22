"""Tests of the range table (plan WP5 step 2)."""

from __future__ import annotations

import pytest

from validation.rules import (
    DEFAULT_ABS_FLOOR,
    DEFAULT_REL_TOLERANCE,
    FIELD_RULES,
    rule_for,
    tolerance_for,
    values_agree,
)

#: The documented bounds, in the unit a human reads them in.
DOCUMENTED_RANGES: dict[str, tuple[str | None, float, float]] = {
    "vds_max": ("V", 1.0, 2000.0),
    "id_continuous": ("A", 0.01, 1000.0),
    "rds_on": ("ohm", 0.0001, 100.0),
    "vgs_threshold": ("V", 0.1, 5.0),
    "vgs_max": ("V", 1.0, 50.0),
    "total_gate_charge_qg": ("C", 0.01e-9, 2000e-9),
    "gate_drain_charge_qgd": ("C", 0.01e-9, 1000e-9),
    "input_capacitance_ciss": ("F", 1e-12, 100000e-12),
    "output_capacitance_coss": ("F", 1e-12, 100000e-12),
    "max_junction_temp": ("degC", 25.0, 300.0),
    "thermal_resistance": ("degC/W", 0.01, 200.0),
    "reverse_recovery_qrr": ("C", 0.1e-9, 100000e-9),
    "supply_voltage_min": ("V", 0.5, 100.0),
    "supply_voltage_max": ("V", 1.0, 200.0),
    "peak_source_current": ("A", 0.05, 200.0),
    "peak_sink_current": ("A", 0.05, 200.0),
    "input_logic_level": ("V", 0.0, 10.0),
    "propagation_delay": ("s", 1e-9, 100000e-9),
    "rise_time": ("s", 1e-9, 100000e-9),
    "fall_time": ("s", 1e-9, 100000e-9),
    "uvlo_threshold": ("V", 0.5, 100.0),
    "channel_count": (None, 1.0, 8.0),
    "operating_temp_min": ("degC", -100.0, 25.0),
    "operating_temp_max": ("degC", 40.0, 300.0),
}


@pytest.mark.parametrize(("name", "expected"), DOCUMENTED_RANGES.items())
def test_the_range_table_matches_the_specification(
    name: str, expected: tuple[str | None, float, float]
) -> None:
    unit, minimum, maximum = expected
    rule = rule_for(name)
    assert rule is not None, f"{name} has no rule"
    assert rule.unit == unit
    assert rule.minimum == pytest.approx(minimum)
    assert rule.maximum == pytest.approx(maximum)
    assert rule.note, f"{name} has no documentation"


def test_package_is_never_range_checked() -> None:
    rule = rule_for("package")
    assert rule is not None
    assert rule.unit is None
    assert not rule.has_range


def test_an_unknown_name_has_no_rule() -> None:
    assert rule_for("something_else") is None
    assert rule_for(None) is None
    assert rule_for("") is None


def test_channel_count_must_be_a_whole_number() -> None:
    rule = rule_for("channel_count")
    assert rule is not None
    assert rule.integer
    assert rule.is_integer(2.0)
    assert not rule.is_integer(2.5)


def test_the_range_check_is_inclusive() -> None:
    rule = rule_for("vds_max")
    assert rule is not None
    assert rule.in_range(1.0)
    assert rule.in_range(2000.0)
    assert not rule.in_range(0.999)
    assert not rule.in_range(2000.001)


def test_capacitance_has_a_looser_tolerance() -> None:
    rel_tolerance, _ = tolerance_for("input_capacitance_ciss")
    assert rel_tolerance == 0.10
    rel_tolerance, _ = tolerance_for("vds_max")
    assert rel_tolerance == DEFAULT_REL_TOLERANCE == 0.05


def test_an_unknown_field_uses_the_default_tolerance() -> None:
    assert tolerance_for("something_else") == (DEFAULT_REL_TOLERANCE, DEFAULT_ABS_FLOOR)


def test_values_agree() -> None:
    assert values_agree(100.0, 102.0)
    assert not values_agree(100.0, 160.0)
    assert not values_agree(100.0, 0.0)
    # the absolute floor keeps tiny values from failing on floating point noise
    assert values_agree(1e-12, 0.0, abs_floor=1e-9)
    assert values_agree(1e-12, 1.0000001e-12, abs_floor=1e-9)


def test_every_rule_documents_itself() -> None:
    for name, rule in FIELD_RULES.items():
        assert rule.name == name
        assert rule.note
