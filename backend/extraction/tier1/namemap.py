"""Symbol / label -> standard parameter name matching (tier 1).

The matcher never guesses: a row label that does not match confidently
returns ``None`` and the field ends up in ``failed_fields``.

An optional ``lookup`` callable can be injected so that the database agent's
``name_map`` table becomes the authority at integration time.

Owner: agent b-tier1.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from shared.schemas import Family, GateDriverSpec, MosfetSpec

from .parsing import clean_cell

__all__ = [
    "FAMILY_FIELDS",
    "NameMatch",
    "NameMap",
    "NameLookup",
    "STANDARD_NAMES",
    "load_name_map",
    "lookup_from_rows",
    "match_name",
    "normalise_label",
    "normalise_symbol",
]

#: Every standard parameter name of the project, per family.
FAMILY_FIELDS: dict[Family, tuple[str, ...]] = {
    Family.MOSFET: tuple(MosfetSpec.model_fields),
    Family.GATE_DRIVER: tuple(GateDriverSpec.model_fields),
}

#: All standard names (both families).
STANDARD_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(name for names in FAMILY_FIELDS.values() for name in names)
)

# Compound rows: one table row that carries two standard names.
SUPPLY_NAMES = ("supply_voltage_min", "supply_voltage_max")
TEMP_RANGE_NAMES = ("operating_temp_min", "operating_temp_max")

# Symbol -> standard name.  The key is the normalised symbol
# (upper case, no spaces, parentheses kept).
SYMBOL_ALIASES: dict[str, str | tuple[str, ...]] = {
    # --- MOSFET -----------------------------------------------------------
    "VDS": "vds_max",
    "VDSS": "vds_max",
    "VDSMAX": "vds_max",
    "ID": "id_continuous",
    "IDC": "id_continuous",
    "RDS(ON)": "rds_on",
    "RDSON": "rds_on",
    "RDS(ON)MAX": "rds_on",
    "VGS(TH)": "vgs_threshold",
    "VGSTH": "vgs_threshold",
    "VTH": "vgs_threshold",
    "VGS": "vgs_max",
    "VGSS": "vgs_max",
    "QG": "total_gate_charge_qg",
    "QGTOTAL": "total_gate_charge_qg",
    "QGD": "gate_drain_charge_qgd",
    "CISS": "input_capacitance_ciss",
    "CIN": "input_capacitance_ciss",
    "COSS": "output_capacitance_coss",
    "COUT": "output_capacitance_coss",
    "TJ": "max_junction_temp",
    "TJMAX": "max_junction_temp",
    "RTHJC": "thermal_resistance",
    "RTH": "thermal_resistance",
    "RTHJA": "thermal_resistance",
    "QRR": "reverse_recovery_qrr",
    # --- gate driver ------------------------------------------------------
    "VCC": SUPPLY_NAMES,
    "VDD": SUPPLY_NAMES,
    "VS": SUPPLY_NAMES,
    "IO+": "peak_source_current",
    "IO-": "peak_sink_current",
    "IOP": "peak_source_current",
    "ION": "peak_sink_current",
    "VIL": "input_logic_level",
    "VIH": "input_logic_level",
    "VIN": "input_logic_level",
    "TPD": "propagation_delay",
    "TPLH": "propagation_delay",
    "TPHL": "propagation_delay",
    "TR": "rise_time",
    "TF": "fall_time",
    "UVLO": "uvlo_threshold",
    "TOPR": TEMP_RANGE_NAMES,
    "TA": TEMP_RANGE_NAMES,
    # --- both -------------------------------------------------------------
    "PACKAGE": "package",
    "PKG": "package",
    "NCH": "channel_count",
}

# Label -> standard name.  The key is the normalised label
# (upper case, punctuation replaced by a single space).
LABEL_ALIASES: dict[str, str | tuple[str, ...]] = {
    # --- MOSFET -----------------------------------------------------------
    "DRAIN SOURCE VOLTAGE": "vds_max",
    "DRAIN TO SOURCE VOLTAGE": "vds_max",
    "DRAIN SOURCE VOLTAGE VDS": "vds_max",
    "CONTINUOUS DRAIN CURRENT": "id_continuous",
    "CONTINUOUS DRAIN CURRENT ID": "id_continuous",
    "DRAIN CURRENT": "id_continuous",
    "MAXIMUM JUNCTION TEMPERATURE": "max_junction_temp",
    "JUNCTION TEMPERATURE": "max_junction_temp",
    "MAX JUNCTION TEMPERATURE": "max_junction_temp",
    "OPERATING JUNCTION TEMPERATURE": "max_junction_temp",
    "DRAIN SOURCE ON RESISTANCE": "rds_on",
    "DRAIN SOURCE ON RESISTANCE RDS ON": "rds_on",
    "ON RESISTANCE": "rds_on",
    "STATIC ON RESISTANCE": "rds_on",
    "GATE SOURCE THRESHOLD VOLTAGE": "vgs_threshold",
    "GATE THRESHOLD VOLTAGE": "vgs_threshold",
    "THRESHOLD VOLTAGE": "vgs_threshold",
    "GATE SOURCE VOLTAGE": "vgs_max",
    "GATE SOURCE VOLTAGE RATING": "vgs_max",
    "GATE VOLTAGE": "vgs_max",
    "TOTAL GATE CHARGE": "total_gate_charge_qg",
    "GATE CHARGE TOTAL": "total_gate_charge_qg",
    "GATE DRAIN CHARGE": "gate_drain_charge_qgd",
    "GATE SOURCE CHARGE": "gate_drain_charge_qgd",
    "INPUT CAPACITANCE": "input_capacitance_ciss",
    "INPUT CAPACITANCE CISS": "input_capacitance_ciss",
    "OUTPUT CAPACITANCE": "output_capacitance_coss",
    "OUTPUT CAPACITANCE COSS": "output_capacitance_coss",
    "THERMAL RESISTANCE": "thermal_resistance",
    "THERMAL RESISTANCE JUNCTION TO CASE": "thermal_resistance",
    "THERMAL RESISTANCE JUNCTION TO CASE RTHJC": "thermal_resistance",
    "REVERSE RECOVERY CHARGE": "reverse_recovery_qrr",
    "REVERSE RECOVERY": "reverse_recovery_qrr",
    # --- gate driver ------------------------------------------------------
    "SUPPLY VOLTAGE": SUPPLY_NAMES,
    "SUPPLY VOLTAGE VCC": SUPPLY_NAMES,
    "OPERATING SUPPLY VOLTAGE": SUPPLY_NAMES,
    "RECOMMENDED SUPPLY VOLTAGE": SUPPLY_NAMES,
    "PEAK SOURCE CURRENT": "peak_source_current",
    "OUTPUT CURRENT SOURCE": "peak_source_current",
    "SOURCE CURRENT": "peak_source_current",
    "PEAK SINK CURRENT": "peak_sink_current",
    "OUTPUT CURRENT SINK": "peak_sink_current",
    "SINK CURRENT": "peak_sink_current",
    "INPUT LOW LEVEL VOLTAGE": "input_logic_level",
    "INPUT HIGH LEVEL VOLTAGE": "input_logic_level",
    "INPUT LOGIC LEVEL": "input_logic_level",
    "LOGIC INPUT LEVEL": "input_logic_level",
    "PROPAGATION DELAY": "propagation_delay",
    "RISE TIME": "rise_time",
    "FALL TIME": "fall_time",
    "UVLO THRESHOLD": "uvlo_threshold",
    "UNDERVOLTAGE LOCKOUT THRESHOLD": "uvlo_threshold",
    "OPERATING TEMPERATURE": TEMP_RANGE_NAMES,
    "OPERATING TEMPERATURE RANGE": TEMP_RANGE_NAMES,
    "AMBIENT TEMPERATURE RANGE": TEMP_RANGE_NAMES,
    # --- both -------------------------------------------------------------
    "PACKAGE": "package",
    "PACKAGE TYPE": "package",
    "PACKAGING": "package",
    "NUMBER OF CHANNELS": "channel_count",
    "CHANNELS": "channel_count",
    "CHANNEL COUNT": "channel_count",
}

# Labels that never denote a parameter (table headers, remarks, ...).
NON_PARAMETER_LABELS = {
    "PARAMETER",
    "PARAMETERS",
    "CHARACTERISTIC",
    "CHARACTERISTICS",
    "SYMBOL",
    "MIN",
    "TYP",
    "TYPICAL",
    "MAX",
    "UNIT",
    "UNITS",
    "CONDITION",
    "CONDITIONS",
    "TEST CONDITION",
    "TEST CONDITIONS",
    "VALUE",
    "VALUES",
    "COMMENT",
    "COMMENTS",
    "NOTE",
    "NOTES",
    "REMARKS",
    "DESCRIPTION",
    "ITEM",
    "NAME",
    "RATING",
    "TYP VALUE",
}


class NameLookup(Protocol):
    """A pluggable name authority (e.g. the database ``name_map`` table)."""

    def __call__(self, raw_name: str) -> str | None: ...


@dataclass(frozen=True)
class NameMatch:
    """The outcome of a name match.

    ``names`` holds one standard name or, for a compound row (supply voltage,
    operating temperature), two.
    """

    names: tuple[str, ...]
    confidence: float
    matched_by: str

    @property
    def name(self) -> str:
        return self.names[0]


def normalise_symbol(text: str | None) -> str:
    """Normalise a symbol: upper case, no spaces, parentheses kept."""
    raw = clean_cell(text).upper()
    return re.sub(r"[^A-Z0-9()+\-/]", "", raw)


def normalise_label(text: str | None) -> str:
    """Normalise a label: upper case, punctuation -> space."""
    raw = clean_cell(text).upper()
    raw = raw.replace("°", " ")
    raw = re.sub(r"[^A-Z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _lookup_table(table: dict[str, str | tuple[str, ...]], key: str) -> tuple[str, ...] | None:
    value = table.get(key)
    if value is None:
        return None
    if isinstance(value, tuple):
        return value
    return (value,)


def match_name(
    raw_name: str,
    *,
    symbol: str | None = None,
    family: Family | None = None,
    lookup: NameLookup | None = None,
    fuzzy_threshold: float = 90.0,
) -> NameMatch | None:
    """Match a table row (label and/or symbol) to standard name(s).

    Returns ``None`` when nothing matches confidently.  The order is:

    1. the injected ``lookup`` callable (the database ``name_map`` table),
    2. an exact symbol match,
    3. an exact label match,
    4. a fuzzy match (rapidfuzz) with a score of at least ``fuzzy_threshold``.
    """
    label = clean_cell(raw_name)
    sym = clean_cell(symbol) if symbol else ""

    allowed: set[str] | None = None
    if family is not None:
        allowed = set(FAMILY_FIELDS.get(family, ()))

    def _accept(names: tuple[str, ...]) -> tuple[str, ...] | None:
        if allowed is not None and not all(name in allowed for name in names):
            return None
        return names

    if lookup is not None:
        for candidate in (sym, label):
            if not candidate:
                continue
            raw = lookup(candidate)
            if not raw:
                continue
            names = tuple(part.strip() for part in str(raw).split(",") if part.strip())
            accepted = _accept(names)
            if accepted:
                return NameMatch(names=accepted, confidence=0.9, matched_by="injected")

    if not label and not sym:
        return None

    sym_key = normalise_symbol(sym)
    label_key = normalise_label(label)

    if sym_key:
        symbol_names = _lookup_table(SYMBOL_ALIASES, sym_key)
        if symbol_names:
            accepted = _accept(symbol_names)
            if accepted:
                return NameMatch(names=accepted, confidence=0.85, matched_by="symbol")

    if label_key and label_key not in NON_PARAMETER_LABELS:
        label_names = _lookup_table(LABEL_ALIASES, label_key)
        if label_names:
            accepted = _accept(label_names)
            if accepted:
                return NameMatch(names=accepted, confidence=0.85, matched_by="label")

    # --- fuzzy fallback ---------------------------------------------------
    for key, table in (
        (label_key, LABEL_ALIASES),
        (label_key, SYMBOL_ALIASES),
        (sym_key, SYMBOL_ALIASES),
    ):
        if not key:
            continue
        fuzzy = _fuzzy_match(key, table, fuzzy_threshold)
        if fuzzy is None:
            continue
        names, score = fuzzy
        accepted = _accept(names)
        if accepted:
            return NameMatch(names=accepted, confidence=0.70, matched_by="fuzzy")

    return None


def _fuzzy_match(
    key: str,
    table: dict[str, str | tuple[str, ...]],
    threshold: float,
) -> tuple[tuple[str, ...], float] | None:
    """Fuzzy match one key against an alias table (rapidfuzz).

    The match has to reach ``threshold`` and to be unambiguous (the runner-up
    must be clearly worse), otherwise nothing is returned.
    """
    try:
        from rapidfuzz import fuzz, process
    except ImportError:  # pragma: no cover - rapidfuzz is a hard dependency
        return None

    choices = list(table)
    if not choices:
        return None
    results = process.extract(key, choices, scorer=fuzz.token_sort_ratio, limit=2)
    if not results:
        return None
    top_choice, top_score = results[0][0], float(results[0][1])
    if top_score < threshold:
        return None
    if len(results) > 1 and top_score - float(results[1][1]) < 5.0:
        return None  # ambiguous
    names = _lookup_table(table, top_choice)
    if names is None:
        return None
    return names, top_score


def lookup_from_rows(rows: Iterable[Mapping[str, str]]) -> NameLookup:
    """Build a lookup callable from ``name_map`` rows.

    A row is a mapping with a ``raw_name`` and a ``standard_name`` key - the
    shape of the ``name_map`` table of the database layer.  Two standard names
    can be given as ``"supply_voltage_min,supply_voltage_max"`` for a row that
    carries a range.
    """
    table: dict[str, str] = {}
    for row in rows:
        raw = str(row.get("raw_name") or "").strip()
        standard = str(row.get("standard_name") or "").strip()
        if raw and standard:
            table.setdefault(raw, standard)

    def lookup(raw_name: str) -> str | None:
        key = str(raw_name or "").strip()
        if key in table:
            return table[key]
        return table.get(key.lower())

    return lookup


def load_name_map(path: str | Path) -> NameLookup:
    """Load the ``name_map`` export of the database layer (a JSON file).

    The file holds ``{"name_map": [{"raw_name": ..., "standard_name": ...}]}``
    or a plain list of such rows.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("name_map", []) if isinstance(payload, dict) else payload
    return lookup_from_rows(rows)


class NameMap:
    """The tier-1 name matcher.

    Parameters
    ----------
    lookup:
        Optional callable ``lookup(raw_name) -> str | None``.  When given it
        becomes the authority and is consulted before the built-in alias
        tables (this is how the database agent injects the ``name_map``
        table during integration).
    fuzzy_threshold:
        Minimum rapidfuzz score for the fuzzy fallback (default 90).
    """

    def __init__(
        self,
        lookup: NameLookup | None = None,
        *,
        fuzzy_threshold: float = 90.0,
        family: Family | None = None,
    ) -> None:
        self.lookup = lookup
        self.fuzzy_threshold = fuzzy_threshold
        self.family = family

    def match(
        self,
        raw_name: str,
        *,
        symbol: str | None = None,
        family: Family | None = None,
    ) -> NameMatch | None:
        """Match one row; see :func:`match_name`."""
        return match_name(
            raw_name,
            symbol=symbol,
            family=family or self.family,
            lookup=self.lookup,
            fuzzy_threshold=self.fuzzy_threshold,
        )

    def match_symbol(self, symbol: str | None, *, family: Family | None = None) -> str | None:
        """Return the standard name of a symbol, or ``None``."""
        if not symbol:
            return None
        match = self.match(symbol, symbol=symbol, family=family)
        return match.names[0] if match else None
