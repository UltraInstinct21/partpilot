"""Confidence model of the validator (plan WP5 step 6, docs/CONTRACTS.md).

The formula is the contract::

    base      = {tier1: 0.85, tier2: 0.75, tier3: 0.70, api: 0.90, manual: 1.00}
    checks    = 0.10 * (range check passed)
              + 0.05 * (min <= typ <= max)
              + 0.05 * (unit converted)
    api_match = +0.05 when the API value agrees within tolerance,
                -0.10 when it disagrees
    confidence = clamp(base + checks + api_match, 0.0, 1.0)

A check only contributes when it was *applicable*: the range bonus needs a
field that has a range rule, the ordering bonus needs at least two of
min/typ/max, and the unit bonus needs a unit that actually had to be
converted into the canonical unit.
"""

from __future__ import annotations

from typing import Final

from shared.schemas import ExtractionMethod

__all__ = [
    "API_DISAGREEMENT_PENALTY",
    "API_MATCH_BONUS",
    "BASE_CONFIDENCE",
    "CHECK_ORDERING",
    "CHECK_RANGE",
    "CHECK_UNIT",
    "REVIEW_THRESHOLD",
    "ApiMatch",
    "compute_confidence",
]

#: Base confidence per extraction method.
BASE_CONFIDENCE: Final[dict[ExtractionMethod, float]] = {
    ExtractionMethod.TIER1: 0.85,
    ExtractionMethod.TIER2: 0.75,
    ExtractionMethod.TIER3: 0.70,
    ExtractionMethod.API: 0.90,
    ExtractionMethod.MANUAL: 1.00,
}

#: Bonus for a passed range check.
CHECK_RANGE: Final[float] = 0.10
#: Bonus for a passed min <= typ <= max check.
CHECK_ORDERING: Final[float] = 0.05
#: Bonus for a unit that was converted into the canonical unit.
CHECK_UNIT: Final[float] = 0.05
#: Bonus when the API value agrees within the tolerance.
API_MATCH_BONUS: Final[float] = 0.05
#: Penalty when the API value disagrees beyond the tolerance.
API_DISAGREEMENT_PENALTY: Final[float] = 0.10
#: Below this confidence a value always goes to the review queue (FR-10).
REVIEW_THRESHOLD: Final[float] = 0.75

#: How the API cross check ended.
ApiMatch = str  # "none" | "match" | "mismatch"


def compute_confidence(
    method: ExtractionMethod | None,
    *,
    range_ok: bool = False,
    ordering_ok: bool = False,
    unit_ok: bool = False,
    api_match: ApiMatch = "none",
) -> float:
    """Return the confidence of a value.

    Parameters
    ----------
    method:
        The extraction method that produced the value.  ``None`` means "no
        provenance" and results in a base of ``0.0``.
    range_ok:
        The range check was applicable and passed.
    ordering_ok:
        The min <= typ <= max check was applicable and passed.
    unit_ok:
        The unit was understood and converted into the canonical unit.
    api_match:
        ``"match"``, ``"mismatch"`` or ``"none"``.
    """
    base = BASE_CONFIDENCE.get(method, 0.0) if method is not None else 0.0
    checks = 0.0
    if range_ok:
        checks += CHECK_RANGE
    if ordering_ok:
        checks += CHECK_ORDERING
    if unit_ok:
        checks += CHECK_UNIT
    if api_match == "match":
        checks += API_MATCH_BONUS
    elif api_match == "mismatch":
        checks -= API_DISAGREEMENT_PENALTY
    confidence = base + checks
    return max(0.0, min(1.0, confidence))
