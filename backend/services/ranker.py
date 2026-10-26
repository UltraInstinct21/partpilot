"""Component ranking service with support for TypeSafe AI Jev and LangChain.

Ranking strategy:
1. TypeSafe AI Jev (via langchain-typesafe TypeSafeClassifier) when TYPESAFE_API_KEY is configured.
   Jev evaluates relevance probabilities (Noul) and match choices directly without token generation.
2. LangChain Chat Ranker when an LLM provider is active.
3. High-precision Parametric Ranker based on electrical constraint fit, stock, and lifecycle (offline, zero-latency).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shared.schemas import LifecycleStatus, PartSummary, SearchFilter

logger = logging.getLogger(__name__)

__all__ = [
    "ComponentRanker",
    "JevRanker",
    "ParametricRanker",
    "rank_parts",
]


class JevRanker:
    """TypeSafe AI Jev System One decision ranker using langchain-typesafe."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY")
        self._classifier: Any = None
        if self.api_key:
            try:
                from langchain_typesafe import TypeSafeClassifier
                self._classifier = TypeSafeClassifier(api_key=self.api_key)
            except Exception as exc:
                logger.debug("Could not initialize TypeSafeClassifier: %s", exc)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self._classifier is not None)

    def rank(self, query: str, parts: list[PartSummary]) -> list[PartSummary] | None:
        if not self.is_available or not parts:
            return None
        try:
            # Batch evaluate candidates via Jev decision engine
            for part in parts:
                state_desc = (
                    f"Query: {query}\n"
                    f"MPN: {part.mpn}, Manufacturer: {part.manufacturer}, Family: {part.family}\n"
                    f"Package: {part.package or 'unknown'}, Stock: {part.total_stock or 0}\n"
                    f"Parameters: {part.key_parameters or {}}"
                )
                res = self._classifier.invoke(
                    {
                        "state": state_desc,
                        "questions": {
                            "relevance": {
                                "type": "noul",
                                "instructions": (
                                    "The electronic component matches the specifications, "
                                    "electrical parameters, and requirements of the query."
                                ),
                            }
                        },
                    }
                )
                if isinstance(res, dict) and "answers" in res:
                    noul = res["answers"].get("relevance", {}).get("noul")
                    if isinstance(noul, (int, float)):
                        part.score = round(float(noul), 3)

            return sorted(parts, key=lambda p: (-(p.score or 0.0), p.mpn))
        except Exception as exc:
            logger.warning("Jev ranking evaluation failed: %s", exc)
            return None


class ParametricRanker:
    """Deterministic parametric ranker based on electrical metrics, stock and lifecycle."""

    @staticmethod
    def score_part(part: PartSummary, filt: SearchFilter | None, query: str) -> float:
        base_score = 0.50
        key_params = part.key_parameters or {}

        # 1. Family check
        if filt and filt.family and part.family:
            if str(part.family).lower() == str(filt.family).lower():
                base_score += 0.15

        # 2. Constraints check
        if filt and filt.parameters:
            matched_constraints = 0
            for c in filt.parameters:
                val = key_params.get(c.name)
                if val is not None:
                    lower, upper = c.bounds()
                    matches = True
                    if lower is not None and val < lower:
                        matches = False
                    if upper is not None and val > upper:
                        matches = False
                    if matches:
                        matched_constraints += 1
            if filt.parameters:
                ratio = matched_constraints / len(filt.parameters)
                base_score += 0.20 * ratio

        # 3. Stock bonus (up to 0.10)
        stock = part.total_stock or 0
        stock_bonus = min(0.10, (stock / 5000.0) * 0.10)
        base_score += stock_bonus

        # 4. Lifecycle bonus
        if part.lifecycle_status == LifecycleStatus.ACTIVE:
            base_score += 0.05
        elif part.lifecycle_status == LifecycleStatus.OBSOLETE:
            base_score -= 0.30

        # 5. Exact MPN bonus
        q_clean = query.strip().upper()
        if part.mpn and (part.mpn.upper() == q_clean or q_clean in part.mpn.upper()):
            base_score += 0.20

        return max(0.01, min(0.99, round(base_score, 3)))

    def rank(self, query: str, parts: list[PartSummary], filt: SearchFilter | None = None) -> list[PartSummary]:
        for part in parts:
            part.score = self.score_part(part, filt, query)
        return sorted(parts, key=lambda p: (-(p.score or 0.0), p.mpn))


class ComponentRanker:
    """Unified ranker combining Jev (via LangChain), LLM, and parametric scoring."""

    def __init__(self) -> None:
        self.jev = JevRanker()
        self.parametric = ParametricRanker()

    def rank(
        self,
        query: str,
        parts: list[PartSummary],
        filt: SearchFilter | None = None,
    ) -> list[PartSummary]:
        if not parts:
            return []

        # 1. Try TypeSafe Jev ranker if configured
        if self.jev.is_available:
            ranked = self.jev.rank(query, parts)
            if ranked:
                return ranked

        # 2. Use Parametric Ranker
        return self.parametric.rank(query, parts, filt)


_DEFAULT_RANKER = ComponentRanker()


def rank_parts(
    query: str,
    parts: list[PartSummary],
    filt: SearchFilter | None = None,
) -> list[PartSummary]:
    """Rank a list of parts according to query relevance and technical parameters."""
    return _DEFAULT_RANKER.rank(query, parts, filt)
