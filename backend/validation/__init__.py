"""Validation of extracted PartPilot values (plan WP5, FR-06 / FR-07 / FR-08 / FR-10).

Public API
----------
``ParameterValidator``
    Implements the frozen :class:`shared.interfaces.Validator` protocol.
``ValidationOutcome``
    The result of a validation including the human readable reasons.
``get_validator``
    The shared, default validator instance.
``normalize`` / ``canonical_unit_for``
    Unit helpers (FR-06).
``NameMatcher``
    Fuzzy mapping of a raw datasheet name onto a standard parameter name.
``FIELD_RULES`` / ``FieldRule``
    The per-field range table (FR-07).
"""

from __future__ import annotations

from .confidence import BASE_CONFIDENCE, compute_confidence
from .namemap import DEFAULT_ALIASES, NameMatcher
from .rules import FIELD_RULES, FieldRule, rule_for, tolerance_for, values_agree
from .units import CANONICAL_UNITS, PARAMETER_UNITS, canonical_unit_for, normalize, ureg
from .validator import ParameterValidator, ValidationOutcome, get_validator

__all__ = [
    "BASE_CONFIDENCE",
    "CANONICAL_UNITS",
    "DEFAULT_ALIASES",
    "FIELD_RULES",
    "NameMatcher",
    "PARAMETER_UNITS",
    "FieldRule",
    "ParameterValidator",
    "ValidationOutcome",
    "canonical_unit_for",
    "compute_confidence",
    "get_validator",
    "normalize",
    "rule_for",
    "tolerance_for",
    "ureg",
    "values_agree",
]
