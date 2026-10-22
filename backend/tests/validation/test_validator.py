"""The acceptance test of plan WP5.

    "The validator must catch all errors that you add on purpose
     (at least 30 test cases)."

Every row of :data:`WRONG_CASES` is a value that is wrong on purpose.  The
table is driven: the test checks the status **and** that the reason mentions
what actually went wrong.
"""

from __future__ import annotations

import pytest

from shared.schemas import ExtractionMethod, ParameterValue, ValueStatus
from validation.validator import ParameterValidator

TIER1 = ExtractionMethod.TIER1
TIER2 = ExtractionMethod.TIER2
TIER3 = ExtractionMethod.TIER3


def value(
    name: str,
    number: float | None = None,
    unit: str | None = None,
    *,
    value_min: float | None = None,
    value_typ: float | None = None,
    value_max: float | None = None,
    method: ExtractionMethod | None = TIER1,
) -> ParameterValue:
    """Build a parameter value with provenance."""
    return ParameterValue(
        name=name,
        value=number,
        value_min=value_min,
        value_typ=value_typ,
        value_max=value_max,
        unit=unit,
        method=method,
        source_id="src-datasheet-1",
        page=1,
    )


#: ``(case id, value, expected status, expected reason substring)``
WRONG_CASES: list[tuple[str, ParameterValue, ValueStatus, str]] = [
    # ------------------------------------------------- out of range (FR-07)
    ("vds_max_too_high", value("vds_max", 5000, "V"), ValueStatus.REJECTED, "out of range"),
    ("vds_max_too_low", value("vds_max", 0.5, "V"), ValueStatus.REJECTED, "out of range"),
    (
        "id_continuous_too_low",
        value("id_continuous", 0.001, "A"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "id_continuous_too_high",
        value("id_continuous", 2000, "A"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    ("rds_on_too_high", value("rds_on", 500, "ohm"), ValueStatus.REJECTED, "out of range"),
    (
        "rds_on_too_low",
        value("rds_on", 0.00001, "ohm"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "vgs_threshold_too_low",
        value("vgs_threshold", 0.05, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "vgs_threshold_too_high",
        value("vgs_threshold", 6, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    ("vgs_max_too_high", value("vgs_max", 60, "V"), ValueStatus.REJECTED, "out of range"),
    ("vgs_max_too_low", value("vgs_max", 0.5, "V"), ValueStatus.REJECTED, "out of range"),
    (
        "qg_zero",
        value("total_gate_charge_qg", 0, "nC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "qg_too_high",
        value("total_gate_charge_qg", 5000, "nC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "qgd_zero",
        value("gate_drain_charge_qgd", 0, "nC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "qgd_too_high",
        value("gate_drain_charge_qgd", 5000, "nC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "ciss_zero",
        value("input_capacitance_ciss", 0, "pF"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "ciss_too_high",
        value("input_capacitance_ciss", 200000, "pF"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "ciss_in_nf_out_of_range",
        value("input_capacitance_ciss", 200, "nF"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "coss_zero",
        value("output_capacitance_coss", 0, "pF"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "coss_too_high",
        value("output_capacitance_coss", 500000, "pF"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "tj_max_too_high",
        value("max_junction_temp", 400, "degC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "tj_max_too_low",
        value("max_junction_temp", 10, "degC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "thermal_resistance_too_high",
        value("thermal_resistance", 500, "degC/W"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "thermal_resistance_too_low",
        value("thermal_resistance", 0.001, "degC/W"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "qrr_too_low",
        value("reverse_recovery_qrr", 0.01, "nC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "qrr_too_high",
        value("reverse_recovery_qrr", 200000, "nC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "supply_voltage_min_too_low",
        value("supply_voltage_min", 0.1, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "supply_voltage_min_too_high",
        value("supply_voltage_min", 200, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "supply_voltage_max_too_high",
        value("supply_voltage_max", 500, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "supply_voltage_max_too_low",
        value("supply_voltage_max", 0.5, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "peak_source_current_too_high",
        value("peak_source_current", 500, "A"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "peak_source_current_too_low",
        value("peak_source_current", 0.01, "A"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "peak_sink_current_too_high",
        value("peak_sink_current", 500, "A"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "peak_sink_current_too_low",
        value("peak_sink_current", 0.001, "A"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "input_logic_level_too_high",
        value("input_logic_level", 20, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "propagation_delay_zero",
        value("propagation_delay", 0, "ns"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "propagation_delay_too_high",
        value("propagation_delay", 200000, "ns"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    ("rise_time_too_low", value("rise_time", 0.5, "ns"), ValueStatus.REJECTED, "out of range"),
    ("fall_time_too_low", value("fall_time", 0.5, "ns"), ValueStatus.REJECTED, "out of range"),
    (
        "uvlo_threshold_too_low",
        value("uvlo_threshold", 0.1, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "uvlo_threshold_too_high",
        value("uvlo_threshold", 150, "V"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "operating_temp_min_too_high",
        value("operating_temp_min", 50, "degC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "operating_temp_min_too_low",
        value("operating_temp_min", -150, "degC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "operating_temp_max_too_low",
        value("operating_temp_max", 10, "degC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "operating_temp_max_too_high",
        value("operating_temp_max", 400, "degC"),
        ValueStatus.REJECTED,
        "out of range",
    ),
    # ------------------------------------------------- integer and ordering
    (
        "channel_count_zero",
        value("channel_count", 0),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "channel_count_nine",
        value("channel_count", 9),
        ValueStatus.REJECTED,
        "out of range",
    ),
    (
        "channel_count_not_an_integer",
        value("channel_count", 2.5),
        ValueStatus.REJECTED,
        "not an integer",
    ),
    (
        "min_greater_than_typ",
        value("vds_max", None, "V", value_min=100, value_typ=50, value_max=200),
        ValueStatus.REJECTED,
        "min > typ",
    ),
    (
        "typ_greater_than_max",
        value("vds_max", None, "V", value_min=10, value_typ=150, value_max=100),
        ValueStatus.REJECTED,
        "typ > max",
    ),
    (
        "min_greater_than_max",
        value("vds_max", None, "V", value_min=200, value_max=100),
        ValueStatus.REJECTED,
        "min > max",
    ),
    # ------------------------------------------------------- unit problems
    (
        "unknown_unit",
        value("vds_max", 5000, "bananas"),
        ValueStatus.REVIEW,
        "unknown unit",
    ),
    (
        "missing_unit",
        value("vds_max", 56),
        ValueStatus.REVIEW,
        "missing unit",
    ),
    (
        "unit_mismatch_current_field",
        value("id_continuous", 100, "V"),
        ValueStatus.REJECTED,
        "unit mismatch",
    ),
    (
        "unit_mismatch_resistance_field",
        value("rds_on", 12, "V"),
        ValueStatus.REJECTED,
        "unit mismatch",
    ),
    (
        "unit_mismatch_temperature_field",
        value("max_junction_temp", 175, "A"),
        ValueStatus.REJECTED,
        "unit mismatch",
    ),
    # ---------------------------------------------------------- tier review
    (
        "tier2_is_always_reviewed",
        value("vds_max", 56, "V", method=TIER2),
        ValueStatus.REVIEW,
        "needs review",
    ),
    (
        "tier3_is_always_reviewed",
        value("vds_max", 56, "V", method=TIER3),
        ValueStatus.REVIEW,
        "needs review",
    ),
    (
        "tier3_without_a_rule_has_a_low_confidence",
        value("some_unknown_field", 42, None, method=TIER3),
        ValueStatus.REVIEW,
        "low confidence",
    ),
    (
        "missing_method_has_no_provenance",
        value("vds_max", 56, "V", method=None),
        ValueStatus.REVIEW,
        "missing method",
    ),
]


@pytest.fixture()
def validator() -> ParameterValidator:
    return ParameterValidator()


def test_there_are_at_least_thirty_wrong_cases() -> None:
    assert len(WRONG_CASES) >= 30


@pytest.mark.parametrize(
    ("case_id", "value_under_test", "expected_status", "reason"),
    WRONG_CASES,
    ids=[case[0] for case in WRONG_CASES],
)
def test_validator_catches_every_deliberate_error(
    validator: ParameterValidator,
    case_id: str,
    value_under_test: ParameterValue,
    expected_status: ValueStatus,
    reason: str,
) -> None:
    outcome = validator.validate_with_reasons(value_under_test)
    assert outcome.status == expected_status, f"{case_id}: {outcome.reasons}"
    assert any(reason in item for item in outcome.reasons), f"{case_id}: {outcome.reasons}"
    assert outcome.value.status == expected_status


def test_api_disagreement_goes_to_review(validator: ParameterValidator) -> None:
    """A tier-1 value that is 60 % off the API value needs a human."""
    outcome = validator.validate_with_reasons(value("rds_on", 0.012, "ohm"), api_value=0.03)
    assert outcome.status == ValueStatus.REVIEW
    assert any("api value disagrees" in item for item in outcome.reasons)


def test_api_agreement_is_accepted(validator: ParameterValidator) -> None:
    """A tier-1 value that is 2 % off the API value is accepted."""
    outcome = validator.validate_with_reasons(value("rds_on", 0.012, "ohm"), api_value=0.0118)
    assert outcome.status == ValueStatus.ACCEPTED
    assert outcome.reasons == []


def test_valid_tier1_value_is_accepted(validator: ParameterValidator) -> None:
    outcome = validator.validate_with_reasons(value("vds_max", 56, "V"))
    assert outcome.status == ValueStatus.ACCEPTED
    assert outcome.confidence >= 0.85
    assert outcome.reasons == []


def test_package_value_is_accepted_and_does_not_crash(validator: ParameterValidator) -> None:
    package = ParameterValue(
        name="package",
        value=None,
        value_text="TO-220AB",
        method=TIER1,
        source_id="src-datasheet-1",
        page=1,
    )
    outcome = validator.validate_with_reasons(package)
    assert outcome.status == ValueStatus.ACCEPTED
    assert outcome.value.status == ValueStatus.ACCEPTED


def test_channel_count_two_is_accepted(validator: ParameterValidator) -> None:
    outcome = validator.validate_with_reasons(value("channel_count", 2))
    assert outcome.status == ValueStatus.ACCEPTED
    assert outcome.value.status == ValueStatus.ACCEPTED


def test_unknown_field_is_not_rejected(validator: ParameterValidator) -> None:
    """A field without a rule must not disappear."""
    outcome = validator.validate_with_reasons(value("some_new_field", 42, "V"))
    assert outcome.status == ValueStatus.ACCEPTED


def test_accepted_value_keeps_its_provenance(validator: ParameterValidator) -> None:
    outcome = validator.validate_with_reasons(value("vds_max", 56, "V"))
    assert outcome.value.source_id == "src-datasheet-1"
    assert outcome.value.page == 1
    assert outcome.value.method == TIER1


def test_validate_returns_the_value_and_not_the_outcome(validator: ParameterValidator) -> None:
    result = validator.validate(value("vds_max", 5000, "V"))
    assert isinstance(result, ParameterValue)
    assert result.status == ValueStatus.REJECTED
    assert result.confidence > 0.0


def test_validate_many_uses_the_api_values_by_name(validator: ParameterValidator) -> None:
    results = validator.validate_many(
        [
            value("vds_max", 56, "V"),
            value("rds_on", 0.012, "ohm"),
        ],
        api_values={"vds_max": 56.0, "rds_on": 0.5},
    )
    assert [item.status for item in results] == [ValueStatus.ACCEPTED, ValueStatus.REVIEW]


def test_validate_many_returns_one_result_per_value(validator: ParameterValidator) -> None:
    values = [value("vds_max", 56, "V"), value("id_continuous", 3.2, "A")]
    assert len(validator.validate_many(values)) == 2
    assert len(validator.validate_many_with_reasons(values)) == 2


def test_validator_satisfies_the_frozen_protocol(validator: ParameterValidator) -> None:
    from shared.interfaces import Validator

    assert isinstance(validator, Validator)
