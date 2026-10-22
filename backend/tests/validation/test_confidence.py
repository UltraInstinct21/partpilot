"""Tests of the confidence model (plan WP5 step 6)."""

from __future__ import annotations

import pytest

from shared.schemas import ExtractionMethod, ParameterValue, ValueStatus
from validation.confidence import (
    API_DISAGREEMENT_PENALTY,
    API_MATCH_BONUS,
    BASE_CONFIDENCE,
    CHECK_ORDERING,
    CHECK_RANGE,
    CHECK_UNIT,
    REVIEW_THRESHOLD,
    compute_confidence,
)
from validation.validator import ParameterValidator

TIER1 = ExtractionMethod.TIER1


@pytest.mark.parametrize(
    ("method", "base"),
    [
        (ExtractionMethod.TIER1, 0.85),
        (ExtractionMethod.TIER2, 0.75),
        (ExtractionMethod.TIER3, 0.70),
        (ExtractionMethod.API, 0.90),
        (ExtractionMethod.MANUAL, 1.00),
    ],
)
def test_base_confidence(method: ExtractionMethod, base: float) -> None:
    assert BASE_CONFIDENCE[method] == pytest.approx(base)
    assert compute_confidence(method) == pytest.approx(base)


def test_confidence_formula_on_known_inputs() -> None:
    # base only
    assert compute_confidence(TIER1) == pytest.approx(0.85)
    # + range check
    assert compute_confidence(TIER1, range_ok=True) == pytest.approx(0.85 + 0.10)
    # + range + ordering
    assert compute_confidence(TIER1, range_ok=True, ordering_ok=True) == pytest.approx(1.00)
    # + range + unit conversion
    assert compute_confidence(TIER1, range_ok=True, unit_ok=True) == pytest.approx(1.00)
    # + api agreement
    assert compute_confidence(TIER1, range_ok=True, api_match="match") == pytest.approx(1.00)
    # - api disagreement
    assert compute_confidence(TIER1, range_ok=True, api_match="mismatch") == pytest.approx(0.85)
    # no api value at all
    assert compute_confidence(TIER1, range_ok=True, api_match="none") == pytest.approx(0.95)
    # a tier-3 value without any check stays below the review threshold
    assert compute_confidence(ExtractionMethod.TIER3) == pytest.approx(0.70)
    assert compute_confidence(ExtractionMethod.TIER3) < REVIEW_THRESHOLD


def test_confidence_is_clamped() -> None:
    assert compute_confidence(ExtractionMethod.MANUAL, range_ok=True) <= 1.0
    assert compute_confidence(ExtractionMethod.MANUAL, range_ok=True) == pytest.approx(1.0)
    assert compute_confidence(None) == pytest.approx(0.0)
    assert compute_confidence(TIER1, range_ok=True, api_match="mismatch") >= 0.0


def test_the_bonus_constants_match_the_contract() -> None:
    assert CHECK_RANGE == 0.10
    assert CHECK_ORDERING == 0.05
    assert CHECK_UNIT == 0.05
    assert API_MATCH_BONUS == 0.05
    assert API_DISAGREEMENT_PENALTY == 0.10
    assert REVIEW_THRESHOLD == 0.75


def test_validator_confidence_matches_the_formula() -> None:
    """A tier-1 value in a canonical unit: base + range check."""
    validator = ParameterValidator()
    outcome = validator.validate_with_reasons(
        ParameterValue(name="vds_max", value=56, unit="V", method=TIER1)
    )
    assert outcome.confidence == pytest.approx(0.85 + 0.10)


def test_validator_confidence_adds_the_api_bonus() -> None:
    validator = ParameterValidator()
    outcome = validator.validate_with_reasons(
        ParameterValue(name="vds_max", value=56, unit="V", method=TIER1), api_value=56.0
    )
    assert outcome.confidence == pytest.approx(0.85 + 0.10 + 0.05)


def test_validator_confidence_subtracts_on_a_disagreement() -> None:
    validator = ParameterValidator()
    outcome = validator.validate_with_reasons(
        ParameterValue(name="vds_max", value=56, unit="V", method=TIER1), api_value=100.0
    )
    assert outcome.confidence == pytest.approx(0.85 + 0.10 - 0.10)


def test_a_failed_check_gives_no_bonus() -> None:
    """The range and the ordering bonus are only given for a passed check."""
    validator = ParameterValidator()
    outcome = validator.validate_with_reasons(
        ParameterValue(
            name="vds_max",
            value_min=100,
            value_typ=50,
            value_max=200,
            unit="V",
            method=TIER1,
        )
    )
    assert outcome.status == ValueStatus.REJECTED
    # base + range check, but no ordering bonus
    assert outcome.confidence == pytest.approx(0.85 + 0.10)
