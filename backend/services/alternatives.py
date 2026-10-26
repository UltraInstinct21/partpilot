"""Ranked alternative parts (plan WP6, FR-13).

The finder is deliberately deterministic:

1. candidates are the parts of the **same family** with the **same package**
   (when no part of that package exists, the whole family is used);
2. the key fields are compared with a **weighted relative distance**;
3. a candidate that breaks a **hard rule** is rejected (lower voltage rating,
   different family, obsolete, different package);
4. the surviving candidates are ranked, then stock and lifecycle add a small
   bonus;
5. every alternative gets a short reason built from the two biggest
   differences.

The reason is generated locally. An LLM may *polish* it when it is injected and
``explain=True``, but the polished text is rejected when it contains a number
that is not in the input (rule 5: the LLM must never invent a value).
"""

from __future__ import annotations

import logging
import re
from typing import Final

from shared.interfaces import LLMExtractor, PartsRepository
from shared.schemas import (
    AlternativeResult,
    Family,
    LifecycleStatus,
    PartSummary,
    SearchFilter,
)

__all__ = [
    "AlternativesService",
    "GATE_DRIVER_WEIGHTS",
    "MOSFET_WEIGHTS",
    "FIELD_LABELS",
]

#: Weighted distance per family. The weights of one family sum to 1.0.
MOSFET_WEIGHTS: Final[dict[str, float]] = {
    "rds_on": 0.35,
    "vds_max": 0.20,
    "id_continuous": 0.15,
    "total_gate_charge_qg": 0.10,
    "vgs_threshold": 0.10,
    "max_junction_temp": 0.10,
}

GATE_DRIVER_WEIGHTS: Final[dict[str, float]] = {
    "supply_voltage_max": 0.25,
    "supply_voltage_min": 0.10,
    "peak_source_current": 0.20,
    "peak_sink_current": 0.20,
    "propagation_delay": 0.15,
    "rise_time": 0.05,
    "fall_time": 0.05,
}

_FAMILY_WEIGHTS: Final[dict[Family, dict[str, float]]] = {
    Family.MOSFET: MOSFET_WEIGHTS,
    Family.GATE_DRIVER: GATE_DRIVER_WEIGHTS,
}

PACKAGE_ALIASES: Final[dict[str, str]] = {
    "to-220": "TO-220",
    "to-220ab": "TO-220",
    "to-220-3": "TO-220",
    "to220": "TO-220",
    "sot-23": "SOT-23",
    "sot-23-3": "SOT-23",
    "sot23": "SOT-23",
    "to-236": "SOT-23",
    "to-236ab": "SOT-23",
    "to-236-3": "SOT-23",
    "sc-59": "SOT-23",
    "d2pak": "D2PAK",
    "to-263": "D2PAK",
    "to-263ab": "D2PAK",
    "to-263-3": "D2PAK",
    "dpak": "DPAK",
    "to-252": "DPAK",
    "to-252aa": "DPAK",
    "to-252-3": "DPAK",
    "soic-8": "SOIC-8",
    "so-8": "SOIC-8",
    "soic8": "SOIC-8",
    "so8": "SOIC-8",
    "superso8": "SuperSO8",
    "pg-tdson-8": "SuperSO8",
    "powerpak so-8": "SuperSO8",
    "to-92": "TO-92",
    "to-92-3": "TO-92",
}


def canonical_pkg(p: str | None) -> str | None:
    if not p:
        return None
    plow = p.lower().strip()
    for k, v in PACKAGE_ALIASES.items():
        if k in plow:
            return v
    return p


#: Human readable names used in the reason text.
FIELD_LABELS: Final[dict[str, str]] = {
    "rds_on": "Rds(on)",
    "vds_max": "Vds",
    "id_continuous": "Id",
    "total_gate_charge_qg": "Qg",
    "vgs_threshold": "Vgs(th)",
    "max_junction_temp": "Tj(max)",
    "supply_voltage_max": "supply voltage",
    "supply_voltage_min": "supply voltage min",
    "peak_source_current": "source current",
    "peak_sink_current": "sink current",
    "propagation_delay": "prop delay",
    "rise_time": "rise time",
    "fall_time": "fall time",
}

#: The field that must not get worse, per family.
_VOLTAGE_FIELD: Final[dict[Family, str]] = {
    Family.MOSFET: "vds_max",
    Family.GATE_DRIVER: "supply_voltage_max",
}

_LIFECYCLE_BONUS: Final[dict[LifecycleStatus, float]] = {
    LifecycleStatus.ACTIVE: 5.0,
    LifecycleStatus.NRND: 2.0,
    LifecycleStatus.UNKNOWN: 0.0,
    LifecycleStatus.OBSOLETE: 0.0,
}

_NUMBER_RE: Final[re.Pattern[str]] = re.compile(r"-?\d+(?:\.\d+)?")

logger = logging.getLogger(__name__)


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " "))


def _relative_difference(reference: float, candidate: float, cap: float) -> float:
    """Return the relative difference, capped at ``cap``."""
    if reference == 0:
        return 0.0 if candidate == 0 else cap
    rel = abs(candidate - reference) / abs(reference)
    return min(rel, cap)


class AlternativesService:
    """Find and rank alternative parts (FR-13).

    Args:
        repository: the injected :class:`~shared.interfaces.PartsRepository`.
        llm: optional :class:`~shared.interfaces.LLMExtractor` used only to
            *polish* the generated reason when ``explain=True``.
        weights: optional override of the per family weight table.
        stock_bonus: maximum bonus for a large stock.
        stock_target: stock that earns the full stock bonus.
        lifecycle_bonus: bonus for an active part.
        max_relative_difference: cap of the relative difference of one field,
            so a single field can not dominate the distance.
        max_explanations: how many accepted alternatives may be polished by
            the LLM (the LLM costs money, so the number is bounded).
    """

    def __init__(
        self,
        repository: PartsRepository,
        llm: LLMExtractor | None = None,
        provider_discovery: object | None = None,
        *,
        weights: dict[Family, dict[str, float]] | None = None,
        stock_bonus: float = 5.0,
        stock_target: float = 5000.0,
        lifecycle_bonus: float = 5.0,
        max_relative_difference: float = 2.0,
        max_explanations: int = 3,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._provider_discovery = provider_discovery
        self._weights = weights or _FAMILY_WEIGHTS
        self._stock_bonus_max = float(stock_bonus)
        self._stock_target = max(1.0, float(stock_target))
        self._lifecycle_bonus_max = float(lifecycle_bonus)
        self._max_rel = float(max_relative_difference)
        self._max_explanations = max(0, int(max_explanations))

    # -- helpers ----------------------------------------------------------------

    def _values_for(self, summary: PartSummary, needed: set[str]) -> dict[str, float]:
        """Return the parameter values of one part."""
        values: dict[str, float] = {
            name: value for name, value in summary.key_parameters.items() if value is not None
        }
        if not needed.issubset(values.keys()):
            record = self._repository.get_part(summary.part_id)
            if record is not None:
                for parameter in record.parameters:
                    representative = parameter.representative()
                    if representative is not None:
                        values[parameter.name] = representative
        return values

    def _distance(
        self,
        reference: dict[str, float],
        candidate: dict[str, float],
        weights: dict[str, float],
    ) -> tuple[float, dict[str, dict[str, float | None]], list[tuple[str, float]]]:
        """Return the weighted distance, the differences and the ranking list."""
        distance = 0.0
        used_weight = 0.0
        differences: dict[str, dict[str, float | None]] = {}
        contributions: list[tuple[str, float]] = []
        for field, weight in weights.items():
            ref_value = reference.get(field)
            cand_value = candidate.get(field)
            if ref_value is None or cand_value is None:
                continue
            rel = _relative_difference(ref_value, cand_value, self._max_rel)
            distance += weight * rel
            used_weight += weight
            differences[field] = {"reference": ref_value, "candidate": cand_value}
            if rel > 0:
                contributions.append((field, weight * rel))
        if used_weight > 0:
            distance /= used_weight
        contributions.sort(key=lambda item: item[1], reverse=True)
        return distance, differences, contributions

    def _reason(self, differences: dict[str, dict[str, float | None]], contributions) -> str:
        """Build the short reason from the two biggest differences."""
        if not contributions:
            return "matches the reference on all key parameters"
        chunks: list[str] = []
        for field, _ in contributions[:2]:
            ref_value = differences[field]["reference"]
            cand_value = differences[field]["candidate"]
            if ref_value is None or cand_value is None:
                continue
            if cand_value < ref_value:
                chunks.append(f"lower {_label(field)}")
            elif cand_value > ref_value:
                chunks.append(f"higher {_label(field)}")
            else:
                chunks.append(f"same {_label(field)}")
        if not chunks:
            return "matches the reference on all key parameters"
        return ", ".join(chunks)

    def _polish(
        self, reason: str, differences: dict[str, dict[str, float | None]], mpn: str
    ) -> str:
        """Let the LLM polish the reason - but never let it invent a number."""
        if self._llm is None:
            return reason
        try:
            text = self._llm.explain_alternative(differences, mpn)
        except Exception:
            return reason
        if not isinstance(text, str):
            return reason
        text = " ".join(text.strip().split())
        if not text or len(text) > 200:
            return reason
        # Keep one sentence only.
        parts = re.split(r"(?<=[.!?])\s+", text)
        first = parts[0].strip()
        if not first:
            return reason
        if not self._numbers_are_grounded(first, differences):
            return reason
        return first

    @staticmethod
    def _numbers_are_grounded(text: str, differences: dict[str, dict[str, float | None]]) -> bool:
        """Return ``True`` when every number in ``text`` comes from the input."""
        allowed: set[float] = set()
        for entry in differences.values():
            for value in entry.values():
                if value is None:
                    continue
                allowed.add(round(float(value), 6))
                allowed.add(round(float(value) * 1000.0, 6))
                allowed.add(round(float(value) / 1000.0, 6))
        for token in _NUMBER_RE.findall(text):
            try:
                number = float(token)
            except ValueError:  # pragma: no cover - the regex only matches numbers
                continue
            if round(number, 6) not in allowed:
                return False
        return True

    def _stock_points(self, summary: PartSummary) -> float:
        stock = summary.total_stock or 0
        return self._stock_bonus_max * min(1.0, stock / self._stock_target)

    def _lifecycle_points(self, summary: PartSummary) -> float:
        bonus = _LIFECYCLE_BONUS.get(summary.lifecycle_status, 0.0)
        return bonus / 5.0 * self._lifecycle_bonus_max

    # -- protocol ---------------------------------------------------------------

    def alternatives(
        self, part_id: str, limit: int = 10, explain: bool = True
    ) -> list[AlternativeResult]:
        """Return the ranked alternatives for ``part_id``."""
        reference_part = self._repository.get_part(part_id)
        if reference_part is None:
            return []

        # Refresh the candidate pool from configured providers before ranking.
        # Indexed parts remain useful, but are no longer the only source.
        if self._provider_discovery is not None:
            try:
                self._provider_discovery.discover_and_ingest(reference_part.mpn, max(limit * 3, 12))
            except Exception as exc:
                logger.warning("Provider alternative discovery failed: %s", exc)

        family = reference_part.family
        weights = self._weights.get(family, MOSFET_WEIGHTS)
        reference_values = {
            parameter.name: value
            for parameter in reference_part.parameters
            if (value := parameter.representative()) is not None
        }

        summaries, _total = self._repository.list_parts(
            SearchFilter(family=family), limit=1000, offset=0
        )
        candidates = [item for item in summaries if item.part_id != reference_part.part_id]

        # The package is binding when at least one part of the family uses the
        # same package. Otherwise the whole family is used (fallback).
        ref_pkg_canon = canonical_pkg(reference_part.package)
        same_package = [
            item
            for item in candidates
            if reference_part.package is not None
            and (item.package == reference_part.package or (ref_pkg_canon and canonical_pkg(item.package) == ref_pkg_canon))
        ]
        package_is_binding = bool(same_package)
        pool = list(candidates)

        voltage_field = _VOLTAGE_FIELD.get(family)
        reference_voltage = reference_values.get(voltage_field) if voltage_field else None

        accepted: list[AlternativeResult] = []
        rejected: list[AlternativeResult] = []

        for summary in pool:
            values = self._values_for(summary, set(weights))
            distance, differences, contributions = self._distance(reference_values, values, weights)
            reason = self._reason(differences, contributions)

            rejection_reason: str | None = None
            cand_pkg_canon = canonical_pkg(summary.package)
            if summary.family != family:
                rejection_reason = "different family"
            elif summary.lifecycle_status == LifecycleStatus.OBSOLETE:
                rejection_reason = "obsolete part"
            elif (
                voltage_field
                and reference_voltage is not None
                and values.get(voltage_field) is not None
                and values[voltage_field] < reference_voltage
            ):
                rejection_reason = f"lower {_label(voltage_field)} than the reference"
            elif (
                package_is_binding
                and reference_part.package is not None
                and summary.package != reference_part.package
                and (not ref_pkg_canon or cand_pkg_canon != ref_pkg_canon)
            ):
                rejection_reason = f"different package (reference is {reference_part.package})"

            if rejection_reason is not None:
                rejected.append(
                    AlternativeResult(
                        part=summary,
                        score=0.0,
                        rank=0,
                        reason=reason,
                        rejected=True,
                        rejection_reason=rejection_reason,
                        differences=differences,
                    )
                )
                continue

            score = max(0.0, 90.0 * (1.0 - distance))
            score += self._stock_points(summary)
            score += self._lifecycle_points(summary)
            accepted.append(
                AlternativeResult(
                    part=summary,
                    score=round(score, 4),
                    rank=0,
                    reason=reason,
                    rejected=False,
                    rejection_reason=None,
                    differences=differences,
                )
            )

        accepted.sort(key=lambda item: (-item.score, item.part.mpn))
        for index, item in enumerate(accepted, start=1):
            item.rank = index
            if explain and index <= self._max_explanations:
                item.reason = self._polish(item.reason, item.differences, item.part.mpn)

        rejected.sort(key=lambda item: item.part.mpn)
        for index, item in enumerate(rejected, start=len(accepted) + 1):
            item.rank = index

        limit = max(1, int(limit))
        return accepted[:limit] + rejected[:limit]

    def explain_alternative(self, differences: dict[str, dict[str, float | None]], mpn: str) -> str:
        """Public helper: the reason text for one set of differences."""
        contributions = sorted(
            (
                (field, entry.get("reference"), entry.get("candidate"))
                for field, entry in differences.items()
                if entry.get("reference") is not None and entry.get("candidate") is not None
            ),
            key=lambda item: abs((item[2] or 0) - (item[1] or 0)),
            reverse=True,
        )
        chunks: list[str] = []
        for field, ref_value, cand_value in contributions[:2]:
            if cand_value < ref_value:
                chunks.append(f"lower {_label(field)}")
            elif cand_value > ref_value:
                chunks.append(f"higher {_label(field)}")
            else:
                chunks.append(f"same {_label(field)}")
        reason = ", ".join(chunks) if chunks else "matches the reference on all key parameters"
        return self._polish(reason, differences, mpn)
