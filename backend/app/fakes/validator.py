"""A deterministic stand-in for the validator (agent D).

The stub implements the ``Validator`` protocol of ``shared.interfaces`` and
follows the confidence model of ``docs/CONTRACTS.md`` loosely: the base
confidence depends on the extraction tier and a value below 0.75 goes to the
review queue.
"""

from __future__ import annotations

from collections.abc import Iterable

from shared.schemas import (
    ExtractionMethod,
    ParameterValue,
    ValueStatus,
)

_BASE_CONFIDENCE: dict[ExtractionMethod, float] = {
    ExtractionMethod.TIER1: 0.85,
    ExtractionMethod.TIER2: 0.75,
    ExtractionMethod.TIER3: 0.70,
    ExtractionMethod.API: 0.90,
    ExtractionMethod.MANUAL: 1.00,
}

ACCEPT_THRESHOLD = 0.75


class StubValidator:
    """Sets a confidence and a status - it does not convert units."""

    name = "stub-validator"

    def validate(self, value: ParameterValue, api_value: float | None = None) -> ParameterValue:
        """Return a copy of ``value`` with confidence and status set."""
        method = value.method or ExtractionMethod.API
        confidence = _BASE_CONFIDENCE.get(method, 0.5)
        if value.value is None and value.value_typ is None and value.value_max is None:
            confidence = min(confidence, 0.4)
        if api_value is not None and value.value is not None:
            tolerance = max(abs(api_value) * 0.05, 1e-9)
            if abs(value.value - api_value) > tolerance:
                confidence -= 0.10
        confidence = max(0.0, min(1.0, confidence))
        status = ValueStatus.ACCEPTED if confidence >= ACCEPT_THRESHOLD else ValueStatus.REVIEW
        return value.model_copy(update={"confidence": round(confidence, 4), "status": status})

    def validate_many(
        self,
        values: Iterable[ParameterValue],
        api_values: dict[str, float] | None = None,
    ) -> list[ParameterValue]:
        """Validate a batch of values, keyed by standard name for cross-checks."""
        api_values = api_values or {}
        return [self.validate(value, api_values.get(value.name)) for value in values]

    def normalize(self, value: float | None, unit: str | None) -> tuple[float | None, str | None]:
        """Return the value unchanged - the real validator normalises with pint."""
        return value, unit


__all__ = ["StubValidator"]
