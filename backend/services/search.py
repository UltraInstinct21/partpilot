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

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Final

from services.ranker import rank_parts
from shared.interfaces import LLMExtractor, PartsRepository
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    Offer,
    ParameterConstraint,
    ParameterValue,
    PartRecord,
    PartSummary,
    SearchFilter,
    SearchResponse,
    SourceRef,
    SourceType,
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
MAX_LIMIT: Final[int] = 500
MAX_OFFSET: Final[int] = 10_000

#: The budget of the model call inside a search (NFR-04). When the model does
#: not answer in time - the endpoint is down, the network is slow - the
#: deterministic fallback builds the filter instead.
LLM_BUDGET_SECONDS: Final[float] = 4.0
WEB_DISCOVERY_BUDGET_SECONDS: Final[float] = 12.0

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

OPAMP_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"gain_bandwidth", "slew_rate", "input_offset_voltage", "supply_voltage_max", "supply_voltage_min"}
)

REGULATOR_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"v_out", "v_out_min", "v_out_max", "i_out_max", "v_dropout", "v_in_max"}
)

MCU_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"clock_speed", "flash_memory", "ram", "supply_voltage_max", "supply_voltage_min"}
)

GENERAL_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"vr_max", "vrrm_max", "if_max", "trr_ns", "vceo_max", "ic_max", "hfe_min"}
)

ALLOWED_PARAMETERS: Final[frozenset[str]] = (
    MOSFET_PARAMETERS
    | GATE_DRIVER_PARAMETERS
    | OPAMP_PARAMETERS
    | REGULATOR_PARAMETERS
    | MCU_PARAMETERS
    | GENERAL_PARAMETERS
)

_FAMILY_LABELS: Final[dict[Family, str]] = {
    Family.MOSFET: "MOSFET",
    Family.GATE_DRIVER: "gate driver",
    Family.MCU: "microcontroller (MCU)",
    Family.OPAMP: "op-amp",
    Family.REGULATOR: "voltage regulator",
    Family.SENSOR: "sensor",
    Family.TRANSCEIVER: "transceiver",
    Family.PASSIVE: "passive component",
    Family.DIODE: "diode",
    Family.GENERAL: "general component",
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
    text = (query or "").lower().strip()
    if not text:
        return SearchFilter()

    filt = SearchFilter()

    # Family
    if re.search(r"\b(stm32|esp32|mcu|microcontroller|cortex|avr|pic|atmega|rp2040|samd)\b", text):
        filt.family = Family.MCU
    elif re.search(r"\b(opamp|op-amp|operational\s+amplifier|comparator)\b", text):
        filt.family = Family.OPAMP
    elif re.search(r"\b(ldo|voltage\s+regulator|regulator|buck|boost|dcdc|dc-dc)\b", text):
        filt.family = Family.REGULATOR
    elif re.search(r"\b(mosfet|fet|n-channel|p-channel|n-ch|p-ch)\b", text):
        filt.family = Family.MOSFET
    elif re.search(r"\b(gate\s+driver|driver|half-bridge|high-side|low-side)\b", text):
        filt.family = Family.GATE_DRIVER

    # Lifecycle status
    if re.search(r"\bactive\b", text):
        filt.lifecycle_status = [LifecycleStatus.ACTIVE]
    elif re.search(r"\b(out of stock|nrnd)\b", text):
        filt.lifecycle_status = [LifecycleStatus.NRND]
    elif re.search(r"\b(obsolete|discontinued|eol)\b", text):
        filt.lifecycle_status = [LifecycleStatus.OBSOLETE]

    # Availability
    if "in stock" in text or "instock" in text or "available" in text:
        filt.in_stock = True

    # Manufacturer
    KNOWN_MANUFACTURERS = [
        ("infineon", "Infineon Technologies"),
        ("international rectifier", "International Rectifier"),
        (r"\bir\b", "International Rectifier"),
        ("texas instruments", "Texas Instruments"),
        (r"\bti\b", "Texas Instruments"),
        ("onsemi", "onsemi"),
        ("on semi", "onsemi"),
        ("stmicroelectronics", "STMicroelectronics"),
        (r"\bstm?\b", "STMicroelectronics"),
        ("nexperia", "Nexperia"),
        ("vishay", "Vishay Siliconix"),
        ("diodes", "Diodes Incorporated"),
        ("alpha & omega", "Alpha & Omega Semiconductor"),
        (r"\baos\b", "Alpha & Omega Semiconductor"),
        ("microchip", "Microchip Technology"),
        ("analog devices", "Analog Devices / Maxim"),
        (r"\bmaxim\b", "Analog Devices / Maxim"),
        ("renesas", "Renesas Electronics"),
    ]
    for pattern, canonical in KNOWN_MANUFACTURERS:
        if (pattern.startswith(r"\b") and re.search(pattern, text)) or (not pattern.startswith(r"\b") and pattern in text):
            filt.manufacturer = canonical
            break

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

    # A package, for example "in TO-220", "SuperSO8".
    match = re.search(
        r"\b(superso-?8|superso8|to-2[23]0[a-z]*|so-?ic-?\d+|so-?8|powerpak\s*so-?8|tssop-?\d+|htssop-?\d+|sot-?23(?:-\d+)?|d2pak(?:-\d+)?|dpak|to-252|to-263(?:-\d+)?|dfn\d*x?\d*|qfn\d*|dsbga(?:-\d+)?)\b",
        text,
    )
    if match:
        raw_pkg = match.group(1).upper()
        if "SUPERSO" in raw_pkg:
            filt.package = "SuperSO8"
        elif "POWERPAK" in raw_pkg:
            filt.package = "PowerPAK SO-8"
        else:
            filt.package = raw_pkg

    # Specific MPN token detection (e.g. IRF3205S, BSC030N08NS5, UCC27524)
    tokens = [t.strip() for t in re.split(r"[\s,;]+", query) if t.strip()]
    for token in tokens:
        t_low = token.lower()
        if filt.package and t_low in filt.package.lower().replace("-", ""):
            continue
        if filt.manufacturer and t_low in filt.manufacturer.lower():
            continue
        if t_low in {"mosfet", "driver", "active", "nrnd", "stock", "instock", "channel", "n-channel", "p-channel"}:
            continue
        if re.match(r"^[a-zA-Z]{2,}[0-9]+[a-zA-Z0-9_-]*$", token) or re.match(r"^[a-zA-Z]+[0-9]{3,}[a-zA-Z0-9_-]*$", token):
            if not re.match(r"^(to|so|sot|dfn|qfn|v|a|w|m|k|hz)\d+$", t_low):
                filt.mpn_contains = token
                break

    # A plain catalogue term must never degrade into an unfiltered query.
    # Keep the natural text for family-only searches too (for example ESP32
    # should return ESP32 parts, not every MCU in the catalogue).
    has_specific_constraint = bool(
        filt.parameters
        or filt.lifecycle_status
        or filt.in_stock is not None
        or filt.package
        or filt.manufacturer
        or filt.mpn_contains
    )
    generic_catalog_term = bool(
        re.search(
            r"\b(?:esp|esp32|stm|stm32|nrf|arduino|raspberry|raspi|lm\d+|opa\d+|ucc\d+|irf\d+|bsc\d+|mcu|mosfet|opamp|regulator|sensor|driver)\b",
            text,
        )
    )
    if not has_specific_constraint and generic_catalog_term:
        filt.text = text
    elif (
        filt.family is not None
        and generic_catalog_term
        and not filt.parameters
        and not filt.package
        and not filt.mpn_contains
    ):
        filt.text = text


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
    if family is Family.OPAMP:
        return OPAMP_PARAMETERS
    if family is Family.REGULATOR:
        return REGULATOR_PARAMETERS
    if family is Family.MCU:
        return MCU_PARAMETERS
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
        web_discovery: Any | None = None,
        provider_discovery: Any | None = None,
        *,
        max_limit: int = MAX_LIMIT,
        max_offset: int = MAX_OFFSET,
        llm_budget_seconds: float = LLM_BUDGET_SECONDS,
        web_discovery_budget_seconds: float = WEB_DISCOVERY_BUDGET_SECONDS,
    ) -> None:
        self._repository = repository
        self._llm = llm
        self._web_discovery = web_discovery
        self._provider_discovery = provider_discovery
        self._max_limit = max(1, int(max_limit))
        self._max_offset = max(0, int(max_offset))
        self._llm_budget_seconds = max(0.0, float(llm_budget_seconds))
        self._web_discovery_budget_seconds = max(0.0, float(web_discovery_budget_seconds))
        self._llm_last_failed: float = 0.0

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

        # If LLM endpoint failed recently, avoid waiting for repeated timeouts
        if time.time() - self._llm_last_failed < 30.0:
            return fallback_filter(query), False

        try:
            raw: Any = self._call_with_budget(query)
        except TimeoutError:
            self._llm_last_failed = time.time()
            logger.warning(
                "The filter builder did not answer within %.1f s; the query is "
                "parsed by the deterministic fallback.",
                self._llm_budget_seconds,
            )
            return fallback_filter(query), False
        except Exception as exc:
            self._llm_last_failed = time.time()
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
        clean = validate_filter(filt)
        # A model may validly return an empty structured filter for a short
        # catalogue term. Never let that turn a search into "show everything"
        # when the deterministic parser can identify the term safely.
        deterministic = fallback_filter(query)
        if clean == SearchFilter() and deterministic != SearchFilter():
            return deterministic, False
        return clean, True

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

    def _discover_providers_with_budget(self, query: str, limit: int = 50) -> list[Any]:
        if self._provider_discovery is None or not query.strip():
            return []
        from services.web_search import is_blocked
        if is_blocked(query):
            return []
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="partpilot-provider")
        try:
            future = pool.submit(self._provider_discovery.discover_and_ingest, query, limit)
            try:
                value = future.result(timeout=WEB_DISCOVERY_BUDGET_SECONDS)
                return value if isinstance(value, list) else []
            except FuturesTimeoutError:
                future.cancel()
                logger.warning("Provider discovery exceeded %.1f s", WEB_DISCOVERY_BUDGET_SECONDS)
                return []
            except Exception as exc:
                logger.warning("Provider discovery failed: %s", exc)
                return []
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _discover_scraped_with_budget(
        self, query: str, limit: int = 50
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        if self._web_discovery is None or not query.strip() or not hasattr(
            self._web_discovery, "discover_and_ingest_with_results"
        ):
            return [], []
        from services.web_search import is_blocked
        if is_blocked(query):
            return [], []
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="partpilot-scrape")
        try:
            future = pool.submit(self._web_discovery.discover_and_ingest_with_results, query, limit)
            try:
                value = future.result(timeout=WEB_DISCOVERY_BUDGET_SECONDS)
                if isinstance(value, tuple) and len(value) == 2:
                    return value
                return [], []
            except Exception as exc:
                logger.info("Scraped discovery unavailable: %s", exc)
                return [], []
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _process_web_results_to_summaries(
        self,
        web_results: list[dict[str, Any]],
        seen_mpns: set[str],
        query: str = "",
    ) -> list[PartSummary]:
        summaries: list[PartSummary] = []
        for page in web_results:
            if not isinstance(page, dict):
                continue
            mpn = None
            if self._web_discovery is not None and hasattr(self._web_discovery, "_extract_mpn"):
                try:
                    mpn = self._web_discovery._extract_mpn(page, query=query or "")
                except Exception:
                    mpn = None
            if not mpn:
                title_text = f"{page.get('title', '')} {page.get('snippet', '')}".upper()
                tokens = re.findall(r"\b[A-Z0-9]+(?:[-/][A-Z0-9]+)+\b|\b[A-Z0-9]{3,24}\b", title_text)
                for tok in tokens:
                    if sum(1 for c in tok if c.isalpha()) >= 1 and sum(1 for c in tok if c.isdigit()) >= 1:
                        mpn = tok
                        break
            if not mpn or mpn.upper() in seen_mpns:
                continue
            seen_mpns.add(mpn.upper())

            family = Family.GENERAL
            mfg = "Unknown (scraped)"
            pkg = None
            key_params: dict[str, float | None] = {}
            if self._web_discovery is not None:
                if hasattr(self._web_discovery, "_infer_family"):
                    try:
                        family = self._web_discovery._infer_family(page)
                    except Exception:
                        family = Family.GENERAL
                if hasattr(self._web_discovery, "_manufacturer"):
                    try:
                        mfg = self._web_discovery._manufacturer(page)
                    except Exception:
                        mfg = "Unknown (scraped)"
                if hasattr(self._web_discovery, "_extract_package"):
                    try:
                        pkg = self._web_discovery._extract_package(page)
                    except Exception:
                        pkg = None
                if hasattr(self._web_discovery, "_extract_parameters"):
                    try:
                        params = self._web_discovery._extract_parameters(page, family, query=query or "")
                        for p in params:
                            val = p.value if p.value is not None else p.value_typ
                            if val is not None:
                                key_params[p.name] = val
                    except Exception:
                        pass

            offers = page.get("offers") or []
            total_stock = sum(o.get("stock") or 0 for o in offers) if offers else None
            slug = re.sub(r"[^a-z0-9]+", "-", mpn.lower()).strip("-")
            part_id = f"web-{family.value}-{slug}"

            if self._repository is not None:
                source_id = f"web-searxng-{hashlib.sha1(page.get('url', '').encode()).hexdigest()[:12]}"
                try:
                    self._repository.add_source(
                        SourceRef(
                            source_id=source_id,
                            url=page.get("url") or "",
                            type=SourceType.MANUAL,
                            distributor=mfg if mfg != "Unknown (scraped)" else "SearXNG scraped web source",
                            note="Discovered through SearXNG",
                        )
                    )
                    param_objs = [
                        ParameterValue(
                            name=k,
                            value=v,
                            value_typ=v,
                            source_id=source_id,
                            method=ExtractionMethod.SCRAPE,
                            confidence=0.85,
                        )
                        for k, v in key_params.items()
                        if v is not None
                    ]
                    self._repository.add_part(
                        PartRecord(
                            part_id=part_id,
                            mpn=mpn,
                            manufacturer=mfg,
                            family=family,
                            package=pkg,
                            parameters=param_objs,
                            description=page.get("snippet") or page.get("title"),
                            datasheet_url=page.get("url") if str(page.get("url", "")).lower().endswith(".pdf") else None,
                            source_ids=[source_id],
                            offers=[Offer(**{**off, "part_id": part_id}) for off in offers if isinstance(off, dict)],
                        )
                    )
                except Exception as exc:
                    logger.debug("Could not ingest web part %s into repo: %s", part_id, exc)

            summaries.append(
                PartSummary(
                    part_id=part_id,
                    mpn=mpn,
                    manufacturer=mfg,
                    family=family,
                    package=pkg,
                    lifecycle_status=LifecycleStatus.ACTIVE if offers else LifecycleStatus.UNKNOWN,
                    datasheet_url=page.get("url") if str(page.get("url", "")).lower().endswith(".pdf") else None,
                    description=page.get("snippet") or page.get("title"),
                    key_parameters=key_params,
                    offers_count=len(offers),
                    total_stock=total_stock,
                    score=0.85,
                )
            )
        return summaries

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
        scraped_hits, web_results = self._discover_scraped_with_budget(query, limit) if query else ([], [])
        provider_hits = self._discover_providers_with_budget(query, limit) if query else []
        results, total = self._repository.list_parts(filt, limit, offset)
        if scraped_hits or provider_hits or web_results:
            updated_results, total = self._repository.list_parts(filt, limit, offset)
            seen_mpns = {p.mpn.upper() for p in updated_results}
            discovered_summaries: list[PartSummary] = []
            for record in [*scraped_hits, *provider_hits]:
                if record.mpn.upper() not in seen_mpns:
                    seen_mpns.add(record.mpn.upper())
                    key_params: dict[str, float | None] = {}
                    for p in getattr(record, "parameters", []):
                        val = p.value if p.value is not None else p.value_typ
                        if val is not None:
                            key_params[p.name] = val
                    discovered_summaries.append(
                        PartSummary(
                            part_id=record.part_id,
                            mpn=record.mpn,
                            manufacturer=record.manufacturer,
                            family=record.family,
                            package=record.package,
                            lifecycle_status=record.lifecycle_status,
                            datasheet_url=record.datasheet_url,
                            description=record.description,
                            key_parameters=key_params,
                            offers_count=len(record.offers),
                            total_stock=sum(offer.stock or 0 for offer in record.offers),
                            score=0.90,
                        )
                    )
            discovered_summaries.extend(
                self._process_web_results_to_summaries(web_results, seen_mpns, query=query or "")
            )
            results = [*updated_results, *discovered_summaries]
            total = max(total, len(results))

        ai_advisory_dict = None
        # On-demand component discovery: if catalog has 0 hits for a query, discover and ingest live components
        if total == 0 and query and len(query.strip()) >= 2:
            try:
                from services.advisor import ComponentAdvisorService
                advisor = ComponentAdvisorService(self._repository)
                discovered = advisor.discover_and_ingest(query)
                if discovered:
                    results, total = self._repository.list_parts(filt, limit, offset)
                    if total == 0:
                        keyword = query.strip().split()[0]
                        relaxed = SearchFilter(mpn_contains=keyword)
                        results, total = self._repository.list_parts(relaxed, limit, offset)
                        filt = relaxed
            except Exception as exc:
                logger.warning("Component discovery failed: %s", exc)

        # AI Engineering Advisory: generate tradeoffs and recommendations
        if query and len(query.strip()) >= 2:
            try:
                from services.advisor import ComponentAdvisorService
                advisor = ComponentAdvisorService(self._repository)
                advisory = advisor.get_advisory(query)
                if advisory:
                    ai_advisory_dict = advisory.model_dump()
            except Exception as exc:
                logger.warning("AI Advisory generation failed: %s", exc)

        ranked_results = rank_parts(query or "", list(results), filt)
        took_ms = int((time.perf_counter() - started) * 1000)
        return SearchResponse(
            query=query,
            filter=filt,
            results=ranked_results,
            total=int(total),
            limit=limit,
            offset=offset,
            took_ms=took_ms,
            filter_explanation=describe_filter(filt),
            llm_used=llm_used,
            ai_advisory=ai_advisory_dict,
            web_results=web_results,
            provider_candidates=[
                PartSummary(
                    part_id=record.part_id,
                    mpn=record.mpn,
                    manufacturer=record.manufacturer,
                    family=record.family,
                    package=record.package,
                    lifecycle_status=record.lifecycle_status,
                    datasheet_url=record.datasheet_url,
                    description=record.description,
                    offers_count=len(record.offers),
                    total_stock=sum(offer.stock or 0 for offer in record.offers),
                )
                for record in [*scraped_hits, *provider_hits]
            ],
            search_mode=("scraped+providers+catalogue" if scraped_hits and provider_hits else
                         "scraped+catalogue" if scraped_hits else
                         "providers+catalogue+web" if provider_hits and web_results else
                         "providers+catalogue" if provider_hits else
                         "catalogue+web" if web_results else "catalogue"),
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

    def stream_search(
        self, query: str, limit: int = 50, offset: int = 0
    ):
        """Stream search results progressively to reduce waiting time.

        Order of emission:
        1. 'filter': immediately yields parsed structured filter & description
        2. 'local_results': immediately yields local catalogue matches with initial ranking
        3. 'web_results': yields live candidate components scraped from SearXNG & providers
        4. 'discovered_results': on-demand live component ingestion when 0 hits occur
        5. 'advisory': yields AI engineering trade-offs and recommendations
        6. 'done': completion stats
        """
        started = time.perf_counter()
        filt, llm_used = self._build_filter(query or "")
        limit, offset = self._clamp(limit, offset)

        # 1. Immediately yield the parsed filter
        yield {
            "type": "filter",
            "query": query,
            "filter": filt.model_dump(),
            "filter_explanation": describe_filter(filt),
            "llm_used": llm_used,
        }

        # 2. Immediately yield local repository results (zero-wait)
        local_results, total = self._repository.list_parts(filt, limit, offset)
        ranked_local = rank_parts(query or "", list(local_results), filt)
        yield {
            "type": "local_results",
            "results": [p.model_dump() for p in ranked_local],
            "total": total,
            "search_mode": "catalogue",
            "took_ms": int((time.perf_counter() - started) * 1000),
        }

        # 3. Stream web discovery candidates
        scraped_hits, web_results = (
            self._discover_scraped_with_budget(query, limit) if query else ([], [])
        )
        provider_hits = self._discover_providers_with_budget(query, limit) if query else []
        all_hits = [*scraped_hits, *provider_hits]

        if all_hits or web_results:
            updated_results, total = self._repository.list_parts(filt, limit, offset)
            seen_mpns = {p.mpn.upper() for p in updated_results}
            discovered_summaries: list[PartSummary] = []
            for record in all_hits:
                if record.mpn.upper() not in seen_mpns:
                    seen_mpns.add(record.mpn.upper())
                    key_params: dict[str, float | None] = {}
                    for p in getattr(record, "parameters", []):
                        val = p.value if p.value is not None else p.value_typ
                        if val is not None:
                            key_params[p.name] = val
                    discovered_summaries.append(
                        PartSummary(
                            part_id=record.part_id,
                            mpn=record.mpn,
                            manufacturer=record.manufacturer,
                            family=record.family,
                            package=record.package,
                            lifecycle_status=record.lifecycle_status,
                            datasheet_url=record.datasheet_url,
                            description=record.description,
                            key_parameters=key_params,
                            offers_count=len(record.offers),
                            total_stock=sum(offer.stock or 0 for offer in record.offers),
                            score=0.90,
                        )
                    )
            discovered_summaries.extend(
                self._process_web_results_to_summaries(web_results, seen_mpns, query=query or "")
            )
            combined_all = [*updated_results, *discovered_summaries]
            ranked_all = rank_parts(query or "", combined_all, filt)
            total = max(total, len(combined_all))
            yield {
                "type": "web_results",
                "results": [p.model_dump() for p in ranked_all[:limit]],
                "web_results": web_results,
                "provider_candidates": [
                    PartSummary(
                        part_id=record.part_id,
                        mpn=record.mpn,
                        manufacturer=record.manufacturer,
                        family=record.family,
                        package=record.package,
                        lifecycle_status=record.lifecycle_status,
                        datasheet_url=record.datasheet_url,
                        description=record.description,
                        offers_count=len(record.offers),
                        total_stock=sum(offer.stock or 0 for offer in record.offers),
                    ).model_dump()
                    for record in all_hits
                ],
                "total": total,
                "search_mode": "searxng+catalogue",
                "took_ms": int((time.perf_counter() - started) * 1000),
            }

        # 4. On-demand component discovery if 0 hits
        if total == 0 and query and len(query.strip()) >= 2:
            try:
                from services.advisor import ComponentAdvisorService

                advisor = ComponentAdvisorService(self._repository)
                discovered = advisor.discover_and_ingest(query)
                if discovered:
                    updated_results, total = self._repository.list_parts(filt, limit, offset)
                    if total == 0:
                        keyword = query.strip().split()[0]
                        relaxed = SearchFilter(mpn_contains=keyword)
                        updated_results, total = self._repository.list_parts(relaxed, limit, offset)
                        filt = relaxed
                    ranked_disc = rank_parts(query or "", list(updated_results), filt)
                    yield {
                        "type": "discovered_results",
                        "results": [p.model_dump() for p in ranked_disc],
                        "total": total,
                        "took_ms": int((time.perf_counter() - started) * 1000),
                    }
            except Exception as exc:
                logger.warning("Stream discovery failed: %s", exc)

        # 5. AI Advisory
        if query and len(query.strip()) >= 2:
            try:
                from services.advisor import ComponentAdvisorService

                advisor = ComponentAdvisorService(self._repository)
                advisory = advisor.get_advisory(query)
                if advisory:
                    yield {
                        "type": "advisory",
                        "ai_advisory": advisory.model_dump(),
                    }
            except Exception as exc:
                logger.warning("Stream advisory failed: %s", exc)

        # 6. Done event
        yield {
            "type": "done",
            "total": total,
            "took_ms": int((time.perf_counter() - started) * 1000),
        }

    # -- convenience ------------------------------------------------------------

    def describe_filter(self, filt: SearchFilter) -> str:
        """Return the human readable description of ``filt``."""
        return describe_filter(filt)
