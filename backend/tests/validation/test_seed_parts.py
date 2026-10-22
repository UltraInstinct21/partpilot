"""Happy path: the seed parts of the contract fixtures survive the validator.

The fixtures are recorded data, no API is called and no LLM is used.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.schemas import ExtractionMethod, ParameterValue, ValueStatus
from validation.validator import ParameterValidator

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED = REPO_ROOT / "contracts" / "fixtures" / "seed" / "parts.json"


@pytest.fixture(scope="module")
def seed() -> dict:
    return json.loads(SEED.read_text(encoding="utf-8"))


@pytest.fixture()
def validator() -> ParameterValidator:
    return ParameterValidator()


def _parameter_values(part: dict) -> list[ParameterValue]:
    values: list[ParameterValue] = []
    for name, spec in part["parameters"].items():
        values.append(
            ParameterValue(
                part_id=part["part_id"],
                name=name,
                value=spec.get("value"),
                unit=spec.get("unit"),
                condition=spec.get("condition") or {},
                method=ExtractionMethod.TIER1,
                source_id="api-digikey-" + part["part_id"],
                page=1,
            )
        )
    return values


def test_every_seed_parameter_is_accepted(seed: dict, validator: ParameterValidator) -> None:
    for part in seed["parts"]:
        for outcome in validator.validate_many_with_reasons(_parameter_values(part)):
            assert (
                outcome.status == ValueStatus.ACCEPTED
            ), f"{part['mpn']} {outcome.value.name}: {outcome.reasons}"


def test_the_seed_units_are_converted_to_the_canonical_units(
    seed: dict, validator: ParameterValidator
) -> None:
    part = next(item for item in seed["parts"] if item["mpn"] == "IRF3205S")
    outcomes = {
        outcome.value.name: outcome
        for outcome in validator.validate_many_with_reasons(_parameter_values(part))
    }
    # the fixture writes 12 mohm
    assert outcomes["rds_on"].value.value == pytest.approx(0.012)
    assert outcomes["rds_on"].value.unit == "ohm"
    # the fixture writes 37.5 nC
    assert outcomes["total_gate_charge_qg"].value.value == pytest.approx(37.5e-9)
    assert outcomes["total_gate_charge_qg"].value.unit == "C"
    # the fixture writes 8750 pF
    assert outcomes["input_capacitance_ciss"].value.value == pytest.approx(8750e-12)
    assert outcomes["input_capacitance_ciss"].value.unit == "F"
    # the fixture writes 175 degC
    assert outcomes["max_junction_temp"].value.value == pytest.approx(175.0)
    assert outcomes["max_junction_temp"].value.unit == "degC"


def test_the_seed_conditions_travel_with_the_value(
    seed: dict, validator: ParameterValidator
) -> None:
    part = next(item for item in seed["parts"] if item["mpn"] == "IRF3205S")
    outcomes = {
        outcome.value.name: outcome
        for outcome in validator.validate_many_with_reasons(_parameter_values(part))
    }
    assert outcomes["rds_on"].value.condition["Vgs"] == "10 V"
    assert outcomes["rds_on"].value.source_id == "api-digikey-mosfet-irf3205s"
    assert outcomes["rds_on"].value.page == 1


def test_a_seed_value_with_a_broken_number_is_rejected(
    seed: dict, validator: ParameterValidator
) -> None:
    part = next(item for item in seed["parts"] if item["mpn"] == "IRF3205S")
    values = _parameter_values(part)
    for item in values:
        if item.name == "vds_max":
            item.value = 5000.0
    outcomes = {
        outcome.value.name: outcome for outcome in validator.validate_many_with_reasons(values)
    }
    assert outcomes["vds_max"].status == ValueStatus.REJECTED
    assert any("out of range" in reason for reason in outcomes["vds_max"].reasons)
    # the other values of the part are untouched
    assert outcomes["rds_on"].status == ValueStatus.ACCEPTED


def test_a_gate_driver_part_is_accepted(seed: dict, validator: ParameterValidator) -> None:
    driver = next(item for item in seed["parts"] if item["family"] == "gate_driver")
    for outcome in validator.validate_many_with_reasons(_parameter_values(driver)):
        assert (
            outcome.status == ValueStatus.ACCEPTED
        ), f"{driver['mpn']} {outcome.value.name}: {outcome.reasons}"
