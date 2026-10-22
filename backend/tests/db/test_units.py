"""The private unit helper of the data layer."""

from __future__ import annotations

import pytest

from db.units import (
    PARAMETER_UNITS,
    canonical_unit,
    canonicalize,
    is_known_unit,
    unit_scale_map,
)


@pytest.mark.parametrize(
    ("value", "unit", "expected_value", "expected_unit"),
    [
        (56.0, "V", 56.0, "V"),
        (12.0, "mohm", 0.012, "ohm"),
        (5.0, "kohm", 5000.0, "ohm"),
        (37.5, "nC", 3.75e-08, "C"),
        (8750.0, "pF", 8.75e-09, "F"),
        (120.0, "ns", 1.2e-07, "s"),
        (175.0, "degC", 175.0, "degC"),
        (3.7, "degC/W", 3.7, "degC/W"),
        (3.2, "A", 3.2, "A"),
    ],
)
def test_canonicalize(value, unit, expected_value, expected_unit) -> None:
    converted, converted_unit = canonicalize(value, unit)
    assert converted == pytest.approx(expected_value)
    assert converted_unit == expected_unit


def test_canonicalize_keeps_a_value_without_a_unit() -> None:
    assert canonicalize(1.0, None) == (1.0, None)
    assert canonicalize(None, "V") == (None, "V")


def test_canonicalize_keeps_an_unknown_unit() -> None:
    assert canonicalize(1.0, "widgets") == (1.0, "widgets")


def test_canonical_unit_of_an_unknown_unit_is_none() -> None:
    assert canonical_unit("widgets") is None
    assert canonical_unit("mohm") == "ohm"
    assert canonical_unit(None) is None


def test_the_scale_map_only_contains_known_units() -> None:
    scales = unit_scale_map()
    assert scales["mohm"] == pytest.approx(0.001)
    assert scales["ohm"] == pytest.approx(1.0)
    assert "K" not in scales


def test_is_known_unit() -> None:
    assert is_known_unit("mohm") is True
    assert is_known_unit("widgets") is False
    assert is_known_unit(None) is False


def test_the_parameter_registry_covers_the_frozen_spec_models() -> None:
    assert PARAMETER_UNITS["vds_max"] == "V"
    assert PARAMETER_UNITS["rds_on"] == "ohm"
    assert PARAMETER_UNITS["propagation_delay"] == "s"
    assert PARAMETER_UNITS["total_gate_charge_qg"] == "C"
