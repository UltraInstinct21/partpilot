"""Unit tests of the cell parsers (numbers, units, conditions)."""

from __future__ import annotations

import pytest

from extraction.tier1.parsing import (
    extract_label_conditions,
    extract_label_symbol,
    extract_label_unit,
    normalise_condition_key,
    parse_condition,
    parse_number,
    parse_unit,
    parse_value_cell,
)


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5.5", 5.5),
        ("7", 7.0),
        ("1.0e-3", 0.001),
        ("1,234", 1234.0),
        ("1 234", 1234.0),
        ("5,5", 5.5),
        ("1,234,567", 1234567.0),
        ("-40", -40.0),
        ("+12", 12.0),
        ("0.85", 0.85),
        (".5", 0.5),
    ],
)
def test_parse_number_reads_every_notation(text: str, expected: float) -> None:
    assert parse_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["-", "", "  ", "abc", "1.2.3", "typ"])
def test_parse_number_returns_none_for_non_numbers(text: str) -> None:
    assert parse_number(text) is None


# ---------------------------------------------------------------------------
# value cells
# ---------------------------------------------------------------------------
def test_single_number_is_typical() -> None:
    parsed = parse_value_cell("5.5")
    assert parsed.typical == 5.5
    assert parsed.minimum is None
    assert parsed.maximum is None
    assert parsed.point == 5.5
    assert not parsed.is_bound


def test_slash_separated_triple_is_min_typ_max() -> None:
    parsed = parse_value_cell("2 / 3.5 / 4.5")
    assert (parsed.minimum, parsed.typical, parsed.maximum) == (2.0, 3.5, 4.5)


def test_comma_separated_triple_is_min_typ_max() -> None:
    parsed = parse_value_cell("2, 3.5, 4.5")
    assert (parsed.minimum, parsed.typical, parsed.maximum) == (2.0, 3.5, 4.5)


def test_dash_means_not_specified() -> None:
    parsed = parse_value_cell("-")
    assert parsed.minimum is None
    assert parsed.typical is None
    assert parsed.maximum is None
    assert parsed.point is None
    assert not parsed.has_value


def test_max_qualifier_keeps_the_number_as_typical() -> None:
    parsed = parse_value_cell("5.5 max")
    assert parsed.typical == 5.5
    assert parsed.qualifier == "max"


def test_typ_qualifier_keeps_the_number_as_typical() -> None:
    parsed = parse_value_cell("5.5 typ")
    assert parsed.typical == 5.5
    assert parsed.qualifier == "typ"


def test_less_than_is_an_upper_bound() -> None:
    parsed = parse_value_cell("< 0.5")
    assert parsed.comparator == "<"
    assert parsed.maximum == 0.5
    assert parsed.point is None
    assert parsed.is_bound


def test_greater_than_is_a_lower_bound() -> None:
    parsed = parse_value_cell("> 100")
    assert parsed.comparator == ">"
    assert parsed.minimum == 100.0
    assert parsed.point is None
    assert parsed.is_bound


def test_tolerance_is_recorded() -> None:
    parsed = parse_value_cell("±5 %")
    assert parsed.comparator == "±"
    assert parsed.typical == 5.0


def test_range_is_min_and_max() -> None:
    parsed = parse_value_cell("10 - 100")
    assert parsed.minimum == 10.0
    assert parsed.maximum == 100.0
    assert parsed.typical is None


def test_exponent_and_thousands_in_a_value_cell() -> None:
    assert parse_value_cell("1.0e-3").typical == pytest.approx(0.001)
    assert parse_value_cell("1,234").typical == pytest.approx(1234.0)
    assert parse_value_cell("1 234").typical == pytest.approx(1234.0)
    assert parse_value_cell("5,5").typical == pytest.approx(5.5)


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("V", "V"),
        ("mV", "V"),
        ("A", "A"),
        ("mA", "A"),
        ("mOhm", "mohm"),
        ("mΩ", "mohm"),
        ("Ω", "ohm"),
        ("kOhm", "ohm"),
        ("nC", "nC"),
        ("µC", "C"),
        ("pF", "pF"),
        ("nF", "F"),
        ("ns", "ns"),
        ("µs", "s"),
        ("C", "degC"),
        ("°C", "degC"),
        ("C/W", "degC/W"),
    ],
)
def test_parse_unit_returns_the_canonical_unit(text: str, expected: str) -> None:
    unit, _scale = parse_unit(text)
    assert unit == expected


def test_parse_unit_scales_the_value() -> None:
    _unit, scale = parse_unit("mV")
    assert scale == pytest.approx(1e-3)
    _unit, scale = parse_unit("mOhm")
    assert scale == pytest.approx(1.0)


def test_parse_unit_of_an_empty_cell() -> None:
    assert parse_unit("") == (None, 1.0)
    assert parse_unit(None) == (None, 1.0)


def test_unit_in_the_parameter_label_is_honoured() -> None:
    unit, scale = extract_label_unit("Drain-Source On-Resistance (mOhm)")
    assert unit == "mohm"
    assert scale == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# conditions
# ---------------------------------------------------------------------------
def test_parse_condition_splits_and_normalises_the_keys() -> None:
    parsed = parse_condition("VGS = 10 V, ID = 10 A, TJ = 25 C")
    assert parsed == {"Vgs": "10 V", "Id": "10 A", "Tj": "25 C"}


def test_parse_condition_of_an_empty_cell() -> None:
    assert parse_condition("") == {}
    assert parse_condition(None) == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VGS", "Vgs"),
        ("ID", "Id"),
        ("TJ", "Tj"),
        ("VDS", "Vds"),
        ("CL", "Cl"),
        ("RL", "Rl"),
        ("f", "F"),
        ("VCC", "Vcc"),
    ],
)
def test_condition_keys_are_normalised(raw: str, expected: str) -> None:
    assert normalise_condition_key(raw) == expected


def test_condition_in_the_parameter_label() -> None:
    assert extract_label_conditions("Continuous Drain Current (Id) @ 25°C") == {"Tc": "25 C"}


def test_symbol_in_the_parameter_label() -> None:
    assert extract_label_symbol("Continuous Drain Current (Id)") == "Id"


def test_label_without_parenthesis_has_no_symbol() -> None:
    assert extract_label_symbol("Continuous Drain Current") is None
