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

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Final

from shared.interfaces import LLMExtractor, PartsRepository
from shared.schemas import (
    Family,
    LifecycleStatus,
    ParameterConstraint,
    SearchFilter,
    SearchResponse,
)

logger = logging.getLogger("partpilot.services")

__all__ = [
    "ALLOWED_PARAMETERS",
    "GATE_DRIVER_PARAMETERS",
    "MAX_LIMIT",
    "MAX_OFFSET",
    "MOSFET_PARAMETERS",
    "SearchService",
    "describe_filter",
    "fallback_filter",
    "validate_filter",
]

#: Hard pagination limits (NFR-04: a search must answer in <= 5 s).
MAX_LIMIT: Final[int] = 200
MAX_OFFSET: Final[int] = 10_000

#: The budget of the model call inside a search (NFR-04). When the model does
#: not answer in time - the endpoint is down, the network is slow - the
#: deterministic fallback builds the filter instead.
LLM_BUDGET_SECONDS: Final[float] = 4.0

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


def fallback_filter(query: str) -> SearchFilter:
    """Build a filter from a query without a model.

    This is the offline path. It is used when the model is not available: no
    API key, no network, the provider is down, or the model returned
    something that is not a filter.

    It recognises the constraints a user writes most often - the family, a
    voltage, an on-resistance, a charge, a package, "in stock" and a
    manufacturer - and it only ever *builds* a filter. The database still
    chooses the rows, so the rule of the plan ("the LLM must not choose the
    results") holds for the fallback as well.

    A pattern that is not recognised is left out. The fallback never guesses.
    """
    text = (query or "").lower()
    if not text.strip():
        return SearchFilter()

    filt = SearchFilter()

    if "mosfet" in text or "fet" in text:
        filt.family = Family.MOSFET
    elif "driver" in text or "gate driver" in text:
        filt.family = Family.GATE_DRIVER

    if "in stock" in text or "instock" in text or "available" in text:
        filt.in_stock = True
    if "out of stock" in text or "nrnd" in text:
        filt.lifecycle_status = [LifecycleStatus.NRND]

    # A voltage. "100 V N-channel MOSFET" asks for exactly 100 V, while
    # "below 100 V" asks for at most 100 V.
    exact = re.search(
        r"(\d+(?:\.\d+)?)\s*v(?:olts?)?\s*(?:[\w-]+\s+){0,3}?(?:mosfet|fet|driver)\b",
        text,
    )
    if exact:
        filt.parameters.append(
            ParameterConstraint(
                name="vds_max",
                unit="V",
                typ=float(exact.group(1)),
                operator="eq",
            )
        )
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*v(?:olts?)?\b", text)
        if match:
            filt.parameters.append(
                ParameterConstraint(
                    name="vds_max",
                    unit="V",
                    max=float(match.group(1)),
                    operator="lte",
                )
            )

    # An on-resistance, for example "Rds(on) below 5 mOhm".
    match = re.search(
        r"rds\s*\(?\s*on\s*\)?[^0-9]{0,20}(\d+(?:\.\d+)?)\s*(milli-?ohms?|mohm|mω|mΩ)?",
        text,
    )
    if match:
        value = float(match.group(1))
        unit = "mohm" if match.group(2) else "ohm"
        filt.parameters.append(
            ParameterConstraint(
                name="rds_on",
                unit=unit,
                max=value,
                operator="lte",
            )
        )

    # A total gate charge, for example "Qg below 80 nC".
    match = re.search(r"(?:qg|gate charge)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*(nc)?", text)
    if match:
        value = float(match.group(1))
        unit = "nC" if match.group(2) else "C"
        filt.parameters.append(
            ParameterConstraint(
                name="total_gate_charge_qg",
                unit=unit,
                max=value,
                operator="lte",
            )
        )

    # A supply voltage of a gate driver, for example "35 V driver" or
    # "gate driver with a 35 V supply".
    if filt.family is Family.GATE_DRIVER:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*v(?:olts?)?\s*(?:[\w-]+\s+){0,3}?(?:supply|driver)\b",
            text,
        ) or re.search(r"driver[^0-9]{0,20}(\d+(?:\.\d+)?)\s*v(?:olts?)?", text)
        if match:
            filt.parameters.append(
                ParameterConstraint(
                    name="supply_voltage_max",
                    unit="V",
                    max=float(match.group(1)),
                    operator="lte",
                )
            )

    # A package, for example "in TO-220".
    match = re.search(
        r"\b(to-2[23]0[a-z]*|so-?ic-?\d+|so-?8|tssop-?\d+|sot-?23|d2pak|d2pak-\d+)\b", text
    )
    if match:
        filt.package = match.group(1).upper()

    return validate_filter(filt)


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
        llm_budget_seconds: float = LLM_BUDGET_SECONDS,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._max_limit = max(1, int(max_limit))
        self._max_offset = max(0, int(max_offset))
        self._llm_budget_seconds = max(0.0, float(llm_budget_seconds))

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
        """Ask the LLM for a filter. Never raises.

        When the model is not available - no key, no network, the provider is
        down - the query is parsed by the deterministic fallback in
        :func:`fallback_filter`. The fallback only ever *builds* a filter, the
        repository still chooses the rows, so the safety property of the plan
        (the LLM never chooses the results) is kept.

        The model call has a budget (NFR-04: a search answers in 5 seconds or
        less), so a slow or unreachable endpoint does not hold the request.
        """
        if self._llm is None:
            return fallback_filter(query), False
        try:
            raw: Any = self._call_with_budget(query)
        except TimeoutError:
            logger.warning(
                "The filter builder did not answer within %.1f s; the query is "
                "parsed by the deterministic fallback.",
                self._llm_budget_seconds,
            )
            return fallback_filter(query), False
        except Exception as exc:
            # The LLM must never break a search request.
            logger.warning(
                "The filter builder failed (%s: %s); the query is parsed by the "
                "deterministic fallback.",
                type(exc).__name__,
                exc,
            )
            return fallback_filter(query), False
        if raw is None:
            return fallback_filter(query), False
        try:
            filt = SearchFilter.model_validate(raw)
        except Exception as exc:
            logger.warning(
                "The filter builder returned an invalid filter (%s: %s); the query "
                "is parsed by the deterministic fallback.",
                type(exc).__name__,
                exc,
            )
            return fallback_filter(query), False
        return validate_filter(filt), True

    def _call_with_budget(self, query: str) -> Any:
        """Call the filter builder with a time budget.

        The call is synchronous, so it runs in a worker thread. When the budget
        is over, the thread is left to finish on its own - the request does
        not wait for it.
        """
        budget = self._llm_budget_seconds
        if budget <= 0:
            return self._llm.build_search_filter(query)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="partpilot-llm")
        try:
            future = pool.submit(self._llm.build_search_filter, query)
            try:
                return future.result(timeout=budget)
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError("the filter builder ran out of time") from exc
        finally:
            # The thread is left to finish on its own; the request does not
            # wait for it.
            pool.shutdown(wait=False, cancel_futures=True)

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
