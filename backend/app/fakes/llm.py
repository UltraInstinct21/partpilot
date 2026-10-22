"""A deterministic, rule based stand-in for the LLM extractor.

The stub never calls a model and never touches the network. It implements the
``LLMExtractor`` protocol of ``shared.interfaces`` so the API can be used
before the real LLM extractor (agent C) is integrated.

``build_search_filter`` is a small rule based parser. It understands the
examples of the plan, e.g.::

    "100 V MOSFET, Rds(on) below 5 mOhm"
    -> family=mosfet, vds_max <= 100 V, rds_on <= 5 mohm
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from shared.schemas import (
    ExtractionMethod,
    ExtractionResult,
    Family,
    ParameterConstraint,
    SearchFilter,
)

# --- manufacturers ---------------------------------------------------------------

_MANUFACTURERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\binfineon\b", re.I), "Infineon Technologies"),
    (re.compile(r"\bonsemi\b|\bon semi\b", re.I), "onsemi"),
    (re.compile(r"\bst\s?microelectronics\b|\bstmicro\b", re.I), "STMicroelectronics"),
    (re.compile(r"\btexas instruments\b|\bti\b", re.I), "Texas Instruments"),
    (re.compile(r"\bvishay\b", re.I), "Vishay Siliconix"),
    (re.compile(r"\bnexperia\b|\bphilips\b", re.I), "Nexperia"),
    (re.compile(r"\bdiodes incorporated\b|\bdiodes\b", re.I), "Diodes Incorporated"),
    (re.compile(r"\balpha\s*&\s*omega\b|\baos\b", re.I), "Alpha & Omega Semiconductor"),
    (re.compile(r"\brenesas\b", re.I), "Renesas Electronics"),
    (re.compile(r"\bmicrochip\b", re.I), "Microchip Technology"),
    (re.compile(r"\banalog devices\b|\bmaxim\b", re.I), "Analog Devices / Maxim"),
    (re.compile(r"\binternational rectifier\b", re.I), "International Rectifier"),
)

# --- packages --------------------------------------------------------------------

_PACKAGES: tuple[str, ...] = (
    "TO-220AB",
    "TO-263",
    "TO-252",
    "SuperSO8",
    "PowerPAK SO-8",
    "DFN5X6",
    "SO-8",
    "SOT-23-6",
    "SOT-23",
    "SOIC-8",
    "HTSSOP-16",
    "DSBGA-8",
)

# --- raw name -> standard name ---------------------------------------------------

_NAME_MAP: dict[str, str] = {
    "vds": "vds_max",
    "vds max": "vds_max",
    "drain-source voltage": "vds_max",
    "drain source voltage": "vds_max",
    "id": "id_continuous",
    "id continuous": "id_continuous",
    "continuous drain current": "id_continuous",
    "rds(on)": "rds_on",
    "rds on": "rds_on",
    "rds_on": "rds_on",
    "on-resistance": "rds_on",
    "vgs(th)": "vgs_threshold",
    "vgs threshold": "vgs_threshold",
    "threshold voltage": "vgs_threshold",
    "vgs max": "vgs_max",
    "total gate charge": "total_gate_charge_qg",
    "qg": "total_gate_charge_qg",
    "gate-drain charge": "gate_drain_charge_qgd",
    "qgd": "gate_drain_charge_qgd",
    "ciss": "input_capacitance_ciss",
    "input capacitance": "input_capacitance_ciss",
    "coss": "output_capacitance_coss",
    "output capacitance": "output_capacitance_coss",
    "maximum junction temperature": "max_junction_temp",
    "thermal resistance": "thermal_resistance",
    "reverse recovery": "reverse_recovery_qrr",
    "qrr": "reverse_recovery_qrr",
    "supply voltage max": "supply_voltage_max",
    "supply voltage min": "supply_voltage_min",
    "peak source current": "peak_source_current",
    "peak sink current": "peak_sink_current",
    "propagation delay": "propagation_delay",
    "rise time": "rise_time",
    "fall time": "fall_time",
    "uvlo": "uvlo_threshold",
    "channel count": "channel_count",
    "operating temperature min": "operating_temp_min",
    "operating temperature max": "operating_temp_max",
}

_RDS_RE = re.compile(
    r"rds[\s_\-]*\(?\s*on\s*\)?(?P<op>[^0-9]{0,25}?)(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<scale>m|milli|micro|u)?\s*(?:ohms?|Ω)",
    re.I,
)

_VOLT_RE = re.compile(
    r"(?P<op>below|under|less than|up to|at most|max(?:imum)?|at least|above|over|"
    r"more than|min(?:imum)?|greater than)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>v|volt)\b",
    re.I,
)

_CURRENT_RE = re.compile(
    r"(?P<op>below|under|less than|up to|at most|max(?:imum)?|at least|above|over|"
    r"more than|min(?:imum)?|greater than)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>a|amp)\b",
    re.I,
)

_CHARGE_RE = re.compile(
    r"(?P<op>below|under|less than|up to|at most|max(?:imum)?|at least|above|over)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>nc|nc|µc|uc)\b",
    re.I,
)

_LOWER_WORDS = re.compile(r"below|under|less than|up to|at most|max(?:imum)?|<", re.I)
UPPER_WORDS = re.compile(r"above|over|more than|at least|greater than|min(?:imum)?|>", re.I)


def _operator_from(context: str | None) -> str:
    """Map the words around a number to a comparison operator."""
    text = context or ""
    if _LOWER_WORDS.search(text):
        return "lte"
    if UPPER_WORDS.search(text):
        return "gte"
    # A datasheet rating is a maximum unless the query says otherwise.
    return "lte"


class StubLLMExtractor:
    """Deterministic stand-in for the real LLM extractor."""

    name = "stub-llm"

    def extract_tier2(
        self,
        pages: Iterable[tuple[int, str]],
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """The stub never reads a value - it reports every field as failed."""
        page_numbers = [number for number, _ in pages]
        return ExtractionResult(
            part_id=part_id,
            family=family,
            method=ExtractionMethod.TIER2,
            values=[],
            pages_used=page_numbers,
            failed_fields=[],
            notes="Stub extractor: no value is read without a real model.",
            duration_ms=0,
        )

    def extract_tier3(
        self,
        page_images: Iterable[tuple[int, bytes]],
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """The stub never reads a value from an image."""
        pages = [number for number, _ in page_images]
        return ExtractionResult(
            part_id=part_id,
            family=family,
            method=ExtractionMethod.TIER3,
            values=[],
            pages_used=pages,
            notes="Stub extractor: no value is read without a real vision model.",
            duration_ms=0,
        )

    def map_name(self, raw_name: str, family: Family) -> str | None:
        """Map a raw parameter name to a standard name (``None`` when unknown)."""
        key = re.sub(r"\s+", " ", (raw_name or "").strip().lower())
        if key in _NAME_MAP:
            return _NAME_MAP[key]
        for raw, standard in _NAME_MAP.items():
            if raw in key:
                return standard
        return None

    def build_search_filter(self, query: str) -> SearchFilter:
        """Turn a natural-language query into a validated filter."""
        text = (query or "").strip()
        lowered = text.lower()
        filt = SearchFilter()

        # --- family ------------------------------------------------------------
        if re.search(r"\bgate[\s\-_]?driver\b|\bdriver\b", lowered):
            filt.family = Family.GATE_DRIVER
        elif "mosfet" in lowered or "transistor" in lowered:
            filt.family = Family.MOSFET

        # --- manufacturer ------------------------------------------------------
        for pattern, name in _MANUFACTURERS:
            if pattern.search(text):
                filt.manufacturer = name
                break

        # --- package -----------------------------------------------------------
        for package in _PACKAGES:
            if package.lower() in lowered:
                filt.package = package
                break

        # --- stock -------------------------------------------------------------
        if re.search(r"\bout of stock\b|\bnot available\b", lowered):
            filt.in_stock = False
        elif re.search(r"\bin stock\b|\bavailable\b|\bstocked\b", lowered):
            filt.in_stock = True

        constraints: list[ParameterConstraint] = []

        # --- Rds(on) -----------------------------------------------------------
        match = _RDS_RE.search(text)
        if match:
            scale = (match.group("scale") or "").lower()
            unit = (
                "mohm" if scale in {"m", "milli"} else "uohm" if scale in {"u", "micro"} else "ohm"
            )
            constraints.append(
                ParameterConstraint(
                    name="rds_on",
                    unit=unit,
                    max=float(match.group("value")),
                    operator=_operator_from(match.group("op")),
                )
            )

        # --- voltage -----------------------------------------------------------
        match = _VOLT_RE.search(text)
        if match:
            value = float(match.group("value"))
            operator = _operator_from(match.group("op"))
            if "vgs" in lowered:
                name = "vgs_max"
            elif "supply" in lowered or filt.family == Family.GATE_DRIVER:
                name = "supply_voltage_max"
            else:
                name = "vds_max"
            constraint = ParameterConstraint(name=name, unit="V")
            if operator == "gte":
                constraint.min = value
            else:
                constraint.max = value
            constraint.operator = operator
            constraints.append(constraint)

        # --- current -----------------------------------------------------------
        match = _CURRENT_RE.search(text)
        if match and "peak" in lowered:
            value = float(match.group("value"))
            operator = _operator_from(match.group("op"))
            constraint = ParameterConstraint(name="peak_source_current", unit="A")
            if operator == "gte":
                constraint.min = value
            else:
                constraint.max = value
            constraint.operator = operator
            constraints.append(constraint)

        # --- gate charge -------------------------------------------------------
        match = _CHARGE_RE.search(text)
        if match and ("qg" in lowered or "gate charge" in lowered):
            value = float(match.group("value"))
            operator = _operator_from(match.group("op"))
            constraint = ParameterConstraint(name="total_gate_charge_qg", unit="nC")
            if operator == "gte":
                constraint.min = value
            else:
                constraint.max = value
            constraint.operator = operator
            constraints.append(constraint)

        if constraints:
            filt.parameters = constraints
        return filt

    def explain_alternative(self, differences: dict[str, dict[str, float | None]], mpn: str) -> str:
        """Return one short sentence describing the trade-off."""
        if not differences:
            return f"{mpn} is the closest match; no parameter differs."
        names = ", ".join(sorted(differences))
        return f"{mpn} is the closest match; the differing parameters are {names}."


__all__ = ["StubLLMExtractor"]
