"""Natural-language and filter search (plan WP6, FR-11).

The contract is deliberately strict:

* The LLM only **builds** a :class:`~shared.schemas.SearchFilter`.
* The repository always **executes** the filter and chooses the result rows.
* The service validates the filter before it reaches the database, so a
  hallucinated parameter name can never reach a query.

Every collaborator is injected, so the service can be tested with a fake
repository and a fake LLM extractor (no network, no model call).
"""

from __future__ import annotations

import time
from typing import Any, Final

from shared.interfaces import LLMExtractor, PartsRepository
from shared.schemas import (
    Family,
    ParameterConstraint,
    SearchFilter,
    SearchResponse,
)

__all__ = [
    "ALLOWED_PARAMETERS",
    "GATE_DRIVER_PARAMETERS",
    "MAX_LIMIT",
    "MAX_OFFSET",
    "MOSFET_PARAMETERS",
    "SearchService",
    "describe_filter",
    "validate_filter",
]

#: Hard pagination limits (NFR-04: a search must answer in <= 5 s).
MAX_LIMIT: Final[int] = 200
MAX_OFFSET: Final[int] = 10_000

#: Standard parameter names per family. A constraint on anything else is
#: dropped before the filter reaches the database.
MOSFET_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "vds_max",
        "id_continuous",
        "rds_on",
        "vgs_threshold",
        "vgs_max",
        "total_gate_charge_qg",
        "gate_drain_charge_qgd",
        "input_capacitance_ciss",
        "output_capacitance_coss",
        "max_junction_temp",
        "package",
        "thermal_resistance",
        "reverse_recovery_qrr",
    }
)

GATE_DRIVER_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "supply_voltage_min",
        "supply_voltage_max",
        "peak_source_current",
        "peak_sink_current",
        "input_logic_level",
        "propagation_delay",
        "rise_time",
        "fall_time",
        "uvlo_threshold",
        "channel_count",
        "package",
        "operating_temp_min",
        "operating_temp_max",
    }
)

ALLOWED_PARAMETERS: Final[frozenset[str]] = MOSFET_PARAMETERS | GATE_DRIVER_PARAMETERS

_FAMILY_LABELS: Final[dict[Family, str]] = {
    Family.MOSFET: "MOSFET",
    Family.GATE_DRIVER: "gate driver",
}

_OPERATOR_SYMBOLS: Final[dict[str, str]] = {
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "eq": "=",
}


def _num(value: float | None) -> str:
    """Format a number for a human readable filter description."""
    if value is None:
        return "?"
    return f"{value:g}"


def _constraint_text(constraint: ParameterConstraint) -> str:
    """Return ``"<name> <op> <value> <unit>"`` for one constraint."""
    unit = f" {constraint.unit}" if constraint.unit else ""
    operator = constraint.operator
    if operator == "between":
        low = _num(constraint.min) if constraint.min is not None else "-inf"
        high = _num(constraint.max) if constraint.max is not None else "+inf"
        return f"{constraint.name} between {low} and {high}{unit}"
    if operator == "eq":
        value = constraint.typ
        if value is None:
            value = constraint.min if constraint.min is not None else constraint.max
        return f"{constraint.name} = {_num(value)}{unit}"
    symbol = _OPERATOR_SYMBOLS.get(operator, operator)
    bound = constraint.max if operator in ("lt", "lte") else constraint.min
    if bound is None:
        bound = constraint.typ
    return f"{constraint.name} {symbol} {_num(bound)}{unit}"


def describe_filter(filt: SearchFilter) -> str:
    """Turn a filter into one short sentence for the UI.

    Example: ``"MOSFET, vds_max <= 100 V, rds_on <= 5 mohm"``.
    """
    if filt is None:
        return "all parts"
    chunks: list[str] = []
    if filt.family is not None:
        chunks.append(_FAMILY_LABELS.get(filt.family, str(filt.family)))
    if filt.manufacturer:
        chunks.append(f"from {filt.manufacturer}")
    if filt.manufacturer_in:
        chunks.append(f"from {', '.join(filt.manufacturer_in)}")
    if filt.package:
        chunks.append(f"package {filt.package}")
    if filt.package_in:
        chunks.append(f"package {', '.join(filt.package_in)}")
    if filt.lifecycle_status:
        chunks.append("lifecycle " + "/".join(str(s.value) for s in filt.lifecycle_status))
    if filt.in_stock is not None:
        chunks.append("in stock" if filt.in_stock else "out of stock")
    if filt.mpn_contains:
        chunks.append(f"mpn contains '{filt.mpn_contains}'")
    if filt.text:
        chunks.append(f"text '{filt.text}'")
    for constraint in filt.parameters:
        chunks.append(_constraint_text(constraint))
    return ", ".join(chunks) if chunks else "all parts"


def _allowed_for(family: Family | None) -> frozenset[str]:
    if family is Family.MOSFET:
        return MOSFET_PARAMETERS
    if family is Family.GATE_DRIVER:
        return GATE_DRIVER_PARAMETERS
    return ALLOWED_PARAMETERS


def _clean_constraint(
    constraint: ParameterConstraint, family: Family | None
) -> ParameterConstraint | None:
    """Return a usable constraint or ``None`` when it must be dropped."""
    name = (constraint.name or "").strip()
    if not name or name not in _allowed_for(family):
        return None

    operator = constraint.operator
    minimum = constraint.min
    maximum = constraint.max
    typical = constraint.typ

    if operator == "between":
        if minimum is not None and maximum is not None and minimum > maximum:
            # Impossible range: swap the bounds instead of dropping the
            # constraint (a "vds_max <= 100" written upside down is common).
            minimum, maximum = maximum, minimum
        if minimum is None and maximum is None:
            return None
        return constraint.model_copy(update={"name": name, "min": minimum, "max": maximum})

    if operator in ("lt", "lte"):
        bound = maximum if maximum is not None else typical
        if bound is None:
            return None
        return constraint.model_copy(update={"name": name, "max": bound})

    if operator in ("gt", "gte"):
        bound = minimum if minimum is not None else typical
        if bound is None:
            return None
        return constraint.model_copy(update={"name": name, "min": bound})

    if operator == "eq":
        value = typical if typical is not None else minimum
        if value is None:
            value = maximum
        if value is None:
            return None
        return constraint.model_copy(update={"name": name, "typ": value})

    return None


def validate_filter(filt: SearchFilter | None) -> SearchFilter:
    """Return a safe copy of ``filt``.

    * constraints on unknown parameter names are dropped,
    * constraints that cannot be satisfied are repaired (swapped bounds),
    * everything else is left untouched.
    """
    if filt is None:
        return SearchFilter()
    clean = filt.model_copy(deep=True)
    family = clean.family
    kept: list[ParameterConstraint] = []
    for constraint in clean.parameters:
        fixed = _clean_constraint(constraint, family)
        if fixed is not None:
            kept.append(fixed)
    clean.parameters = kept
    return clean


class SearchService:
    """Natural-language search and filter execution (FR-11).

    Args:
        repository: the injected :class:`~shared.interfaces.PartsRepository`.
            It is the only component that chooses the result rows.
        llm: the injected :class:`~shared.interfaces.LLMExtractor`. It may be
            ``None``; the service then only supports :meth:`search_filter`.
        max_limit: upper bound for ``limit``.
        max_offset: upper bound for ``offset``.
    """

    def __init__(
        self,
        repository: PartsRepository,
        llm: LLMExtractor | None = None,
        *,
        max_limit: int = MAX_LIMIT,
        max_offset: int = MAX_OFFSET,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._max_limit = max(1, int(max_limit))
        self._max_offset = max(0, int(max_offset))

    # -- helpers ----------------------------------------------------------------

    def _clamp(self, limit: int, offset: int) -> tuple[int, int]:
        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            limit_value = 50
        try:
            offset_value = int(offset)
        except (TypeError, ValueError):
            offset_value = 0
        limit_value = max(1, min(limit_value, self._max_limit))
        offset_value = max(0, min(offset_value, self._max_offset))
        return limit_value, offset_value

    def _build_filter(self, query: str) -> tuple[SearchFilter, bool]:
        """Ask the LLM for a filter. Never raises."""
        if self._llm is None:
            return SearchFilter(), False
        try:
            raw: Any = self._llm.build_search_filter(query)
        except Exception:
            # The LLM must never break a search request.
            return SearchFilter(), False
        if raw is None:
            return SearchFilter(), False
        try:
            filt = SearchFilter.model_validate(raw)
        except Exception:
            return SearchFilter(), False
        return validate_filter(filt), True

    def _execute(
        self,
        filt: SearchFilter,
        limit: int,
        offset: int,
        *,
        query: str | None = None,
        llm_used: bool = False,
        started: float | None = None,
    ) -> SearchResponse:
        if started is None:
            started = time.perf_counter()
        results, total = self._repository.list_parts(filt, limit, offset)
        took_ms = int((time.perf_counter() - started) * 1000)
        return SearchResponse(
            query=query,
            filter=filt,
            results=list(results),
            total=int(total),
            limit=limit,
            offset=offset,
            took_ms=took_ms,
            filter_explanation=describe_filter(filt),
            llm_used=llm_used,
        )

    # -- protocol ---------------------------------------------------------------

    def search(self, query: str, limit: int = 50, offset: int = 0) -> SearchResponse:
        """Turn ``query`` into a filter and execute it.

        The LLM only builds the filter; the repository executes it. If the LLM
        raises, the search falls back to an empty filter and still answers.
        """
        started = time.perf_counter()
        filt, llm_used = self._build_filter(query or "")
        limit, offset = self._clamp(limit, offset)
        return self._execute(
            filt,
            limit,
            offset,
            query=query,
            llm_used=llm_used,
            started=started,
        )

    def search_filter(self, filt: SearchFilter, limit: int = 50, offset: int = 0) -> SearchResponse:
        """Execute an already built filter - no LLM call.

        This is the path the frontend uses when the user edits the filter
        chips, so the result must not depend on a model.
        """
        started = time.perf_counter()
        clean = validate_filter(filt)
        limit, offset = self._clamp(limit, offset)
        return self._execute(
            clean,
            limit,
            offset,
            query=None,
            llm_used=False,
            started=started,
        )

    # -- convenience ------------------------------------------------------------

    def describe_filter(self, filt: SearchFilter) -> str:
        """Return the human readable description of ``filt``."""
        return describe_filter(filt)
