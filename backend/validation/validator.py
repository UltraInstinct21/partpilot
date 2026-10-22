"""The PartPilot validator (plan WP5, FR-06 / FR-07 / FR-08 / FR-10).

The validator is the last gate before a value reaches the database.  It

* normalises the unit of every value into the canonical unit (FR-06),
* rejects a value that is outside the allowed range of its field (FR-07),
* rejects a value whose min/typ/max are not ordered,
* compares the value with the API value of the same field (FR-08),
* computes a confidence and a status, and sends low confidence values to the
  review queue (FR-10).

The public entry points are :class:`ParameterValidator` (which implements the
frozen :class:`shared.interfaces.Validator` protocol) and
:func:`validation.validator.get_validator`.

Because ``shared.schemas.ParameterValue`` has no field for the reasons, the
reasons are returned by :meth:`ParameterValidator.validate_with_reasons` in a
:class:`ValidationOutcome`.  The frozen schema is never modified.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

from shared.schemas import ExtractionMethod, ParameterValue, ValueStatus

from .confidence import REVIEW_THRESHOLD, compute_confidence
from .namemap import NameMatcher
from .rules import (
    DEFAULT_ABS_FLOOR,
    DEFAULT_REL_TOLERANCE,
    FIELD_RULES,
    FieldRule,
    relative_difference,
    rule_for,
    tolerance_for,
    values_agree,
)
from .units import canonical_unit_for, clean_unit, normalize

__all__ = [
    "ParameterValidator",
    "ValidationOutcome",
    "get_validator",
]

#: The four numeric components of a parameter value.
_COMPONENTS: Final[tuple[str, ...]] = ("value", "value_min", "value_typ", "value_max")

#: The methods that always need a human look.
_ALWAYS_REVIEW_METHODS: Final[frozenset[ExtractionMethod]] = frozenset(
    {ExtractionMethod.TIER2, ExtractionMethod.TIER3}
)


@dataclass
class ValidationOutcome:
    """The result of validating one value.

    Attributes
    ----------
    value:
        The value with the canonical unit, the confidence and the status set.
    status:
        ``accepted`` / ``review`` / ``rejected``.
    confidence:
        The confidence of the value (0.0 .. 1.0).
    reasons:
        Human readable reasons.  Empty for a clean accepted value.
    api_value:
        The API value the value was compared with, when there was one.
    unit:
        The canonical unit of the value.
    """

    value: ParameterValue
    status: ValueStatus
    confidence: float
    reasons: list[str] = field(default_factory=list)
    api_value: float | None = None
    unit: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status == ValueStatus.ACCEPTED

    @property
    def rejected(self) -> bool:
        return self.status == ValueStatus.REJECTED

    @property
    def needs_review(self) -> bool:
        return self.status == ValueStatus.REVIEW


class ParameterValidator:
    """Validate extracted values against the range rules and the API values.

    The class is structural: it satisfies :class:`shared.interfaces.Validator`
    without inheriting from it.

    Parameters
    ----------
    rules:
        The range table.  Defaults to :data:`validation.rules.FIELD_RULES`.
    name_matcher:
        A :class:`validation.namemap.NameMatcher` for the raw name of a value
        (used by the integration, not by the range check itself).
    """

    def __init__(
        self,
        rules: Mapping[str, FieldRule] | None = None,
        name_matcher: NameMatcher | None = None,
    ) -> None:
        self.rules: dict[str, FieldRule] = dict(rules if rules is not None else FIELD_RULES)
        self.name_matcher = name_matcher if name_matcher is not None else NameMatcher()

    # ------------------------------------------------------------- protocol
    def validate(self, value: ParameterValue, api_value: float | None = None) -> ParameterValue:
        """Return a copy of ``value`` with unit, confidence and status set."""
        return self.validate_with_reasons(value, api_value=api_value).value

    def validate_many(
        self,
        values: Iterable[ParameterValue],
        api_values: dict[str, float] | None = None,
    ) -> list[ParameterValue]:
        """Validate a batch of values, keyed by standard name for cross-checks."""
        return [outcome.value for outcome in self.validate_many_with_reasons(values, api_values)]

    def normalize(self, value: float | None, unit: str | None) -> tuple[float | None, str | None]:
        """Convert ``value`` to the canonical unit; return ``(value, unit)``."""
        return normalize(value, unit)

    # --------------------------------------------------------------- extras
    def validate_many_with_reasons(
        self,
        values: Iterable[ParameterValue],
        api_values: dict[str, float] | None = None,
    ) -> list[ValidationOutcome]:
        """Validate a batch and return the full outcomes."""
        outcomes: list[ValidationOutcome] = []
        for value in values:
            api_value = None
            if api_values:
                api_value = api_values.get(value.name)
                if api_value is None:
                    api_value = api_values.get((value.name or "").strip().lower())
            outcomes.append(self.validate_with_reasons(value, api_value=api_value))
        return outcomes

    def validate_with_reasons(
        self,
        value: ParameterValue,
        api_value: float | None = None,
    ) -> ValidationOutcome:
        """Validate one value and return the outcome including the reasons."""
        reasons: list[str] = []
        rejected = False

        name = (value.name or "").strip()
        rule = self.rules.get(name.lower()) or rule_for(name)
        expected_unit = rule.unit if rule is not None else canonical_unit_for(name)

        raw_components = {
            component: number
            for component in _COMPONENTS
            if (number := getattr(value, component, None)) is not None
        }
        has_number = bool(raw_components)

        normalized: dict[str, float] = {}
        canonical_unit: str | None = None
        # none: the value has no number at all (e.g. "package")
        # ok: the unit was understood
        # dimensionless: no unit given, and the field does not want one
        # missing: no unit given, but the field expects one
        # unknown: the unit could not be parsed
        unit_state = "none"

        if has_number:
            if clean_unit(value.unit) is None:
                if expected_unit is None:
                    unit_state = "dimensionless"
                    normalized = dict(raw_components)
                else:
                    unit_state = "missing"
                    reasons.append(f"missing unit for {name} (expected {expected_unit})")
            else:
                unit_state = "ok"
                for component, number in raw_components.items():
                    converted, unit = normalize(number, value.unit, expected_unit=expected_unit)
                    if converted is None:
                        unit_state = "unknown"
                        reasons.append(f"unknown unit '{value.unit}' for {name}")
                        break
                    normalized[component] = converted
                    canonical_unit = unit
                if unit_state == "unknown":
                    normalized = {}

        # A unit that does not belong to the field (a voltage for a current)
        # is a hard error: the range rule of the field cannot be trusted.
        unit_mismatch = False
        if unit_state == "ok" and expected_unit and (canonical_unit or "") != expected_unit:
            unit_mismatch = True
            rejected = True
            reasons.append(
                f"unit mismatch for {name}: expected {expected_unit}, "
                f"got {canonical_unit or 'dimensionless'}"
            )

        # The numbers can be checked when the unit is known.  A value with an
        # unknown or a missing unit is *not* range checked: the number could
        # be in any unit, so the comparison would be a guess.  Such a value
        # goes to the review queue instead.
        numbers_usable = unit_state in ("ok", "dimensionless")

        # ------------------------------------------------------------ range
        range_applicable = (
            rule is not None and rule.has_range and numbers_usable and not unit_mismatch
        )
        range_ok = False
        if range_applicable and rule is not None:
            range_ok = True
            shown_unit = canonical_unit or "dimensionless"
            for component, magnitude in normalized.items():
                if not rule.in_range(magnitude):
                    range_ok = False
                    rejected = True
                    reasons.append(
                        f"out of range: {name} {component}={magnitude:g} {shown_unit} "
                        f"not in [{rule.minimum:g}, {rule.maximum:g}]"
                    )
                if not rule.is_integer(magnitude):
                    range_ok = False
                    rejected = True
                    reasons.append(f"not an integer: {name} {component}={magnitude:g}")

        # --------------------------------------------------------- ordering
        ordering_applicable = False
        ordering_ok = False
        if numbers_usable and not unit_mismatch:
            low = normalized.get("value_min")
            typical = normalized.get("value_typ")
            high = normalized.get("value_max")
            if low is not None and typical is not None:
                ordering_applicable = True
                if low > typical:
                    rejected = True
                    reasons.append(f"ordering violation: {name} min > typ ({low:g} > {typical:g})")
            if typical is not None and high is not None:
                ordering_applicable = True
                if typical > high:
                    rejected = True
                    reasons.append(f"ordering violation: {name} typ > max ({typical:g} > {high:g})")
            if low is not None and high is not None and typical is None:
                ordering_applicable = True
                if low > high:
                    rejected = True
                    reasons.append(f"ordering violation: {name} min > max ({low:g} > {high:g})")
            ordering_ok = ordering_applicable

        # -------------------------------------------------------- API check
        api_state = "none"
        if api_value is not None and numbers_usable and not unit_mismatch:
            representative = self._representative(normalized)
            if representative is not None:
                rel_tolerance, abs_floor = tolerance_for(name)
                if values_agree(representative, api_value, rel_tolerance, abs_floor):
                    api_state = "match"
                else:
                    api_state = "mismatch"
                    difference = relative_difference(representative, api_value) * 100.0
                    shown_unit = canonical_unit or "dimensionless"
                    reasons.append(
                        f"api value disagrees: {name} {representative:g} {shown_unit} "
                        f"vs api {api_value:g} ({difference:.1f}% off, "
                        f"tolerance {rel_tolerance * 100:.0f}%)"
                    )

        # ------------------------------------------------------- confidence
        unit_converted = unit_state == "ok" and self._unit_was_converted(value.unit, canonical_unit)
        method = value.method
        confidence = compute_confidence(
            method,
            range_ok=range_ok,
            ordering_ok=ordering_ok,
            unit_ok=unit_converted,
            api_match=api_state,
        )

        # ----------------------------------------------------------- status
        unit_problem = unit_state == "unknown" or (
            unit_state == "missing" and expected_unit is not None
        )
        if method is None:
            reasons.append("missing method: the value has no provenance")
        elif method in _ALWAYS_REVIEW_METHODS:
            reasons.append(f"method {method.value} needs review")
        if confidence < REVIEW_THRESHOLD:
            reasons.append(f"low confidence {confidence:.2f}")

        if rejected:
            status = ValueStatus.REJECTED
        elif (
            confidence < REVIEW_THRESHOLD
            or api_state == "mismatch"
            or unit_problem
            or method in _ALWAYS_REVIEW_METHODS
            or method is None
        ):
            status = ValueStatus.REVIEW
        else:
            status = ValueStatus.ACCEPTED

        updated = value.model_copy()
        if unit_state == "ok" and normalized:
            updated.unit = canonical_unit
            for component, magnitude in normalized.items():
                setattr(updated, component, magnitude)
        updated.confidence = confidence
        updated.status = status

        return ValidationOutcome(
            value=updated,
            status=status,
            confidence=confidence,
            reasons=reasons,
            api_value=api_value,
            unit=canonical_unit,
        )

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _representative(normalized: Mapping[str, float]) -> float | None:
        """Return the number used for the API comparison.

        The order is the one of
        :meth:`shared.schemas.ParameterValue.representative`: typical, value,
        max, min.
        """
        for component in ("value_typ", "value", "value_max", "value_min"):
            magnitude = normalized.get(component)
            if magnitude is not None:
                return magnitude
        return None

    @staticmethod
    def _unit_was_converted(source_unit: str | None, canonical_unit: str | None) -> bool:
        """Return ``True`` when the source unit had to be converted."""
        cleaned = clean_unit(source_unit)
        if cleaned is None:
            return False
        if canonical_unit is None:
            return False
        return cleaned.lower() != canonical_unit.lower()

    # convenience
    def rule_for(self, name: str | None) -> FieldRule | None:
        """Return the range rule of a standard parameter name."""
        if not name:
            return None
        return self.rules.get(str(name).strip().lower())

    def tolerance(self, name: str | None) -> tuple[float, float]:
        """Return ``(relative_tolerance, absolute_floor)`` of a field."""
        rule = self.rule_for(name)
        if rule is None:
            return (DEFAULT_REL_TOLERANCE, DEFAULT_ABS_FLOOR)
        return (rule.rel_tolerance, rule.abs_floor)


_DEFAULT_VALIDATOR: ParameterValidator | None = None


def get_validator() -> ParameterValidator:
    """Return the shared, default validator instance."""
    global _DEFAULT_VALIDATOR
    if _DEFAULT_VALIDATOR is None:
        _DEFAULT_VALIDATOR = ParameterValidator()
    return _DEFAULT_VALIDATOR
