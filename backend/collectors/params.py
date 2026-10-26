"""Standard parameter names and the vendor label -> standard name mapping.

The standard names are the ones the frozen schema uses
(:class:`shared.schemas.MosfetSpec` and
:class:`shared.schemas.GateDriverSpec`). A distributor sends a *label* and a
*value*; this module turns the label into a standard name and the value into a
number plus a canonical pint unit.

Rules:

* An unknown label maps to ``None``. A value is never attached to a name that
  was only guessed (rule 5 of the project rules and NFR-03).
* :func:`resolve_parameter_name` can optionally use ``rapidfuzz`` for a
  *very* close match (score >= 95). That path is off by default because the
  tier-2 name mapper has to approve a mapping first.
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

__all__ = [
    "CONDITION_KEYS",
    "GATE_DRIVER_PARAMS",
    "MOSFET_PARAMS",
    "STANDARD_PARAMS",
    "UNIT_ALIASES",
    "canonical_unit",
    "infer_family",
    "parse_condition",
    "parse_value_with_unit",
    "resolve_parameter_name",
    "slugify",
]

# --------------------------------------------------------------------------------------
# Standard names
# --------------------------------------------------------------------------------------

MOSFET_PARAMS: frozenset[str] = frozenset(
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

GATE_DRIVER_PARAMS: frozenset[str] = frozenset(
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

STANDARD_PARAMS: frozenset[str] = MOSFET_PARAMS | GATE_DRIVER_PARAMS

#: The canonical unit of every standard parameter (used for a sanity check only).
CANONICAL_UNIT: dict[str, str | None] = {
    "vds_max": "V",
    "id_continuous": "A",
    "rds_on": "ohm",
    "vgs_threshold": "V",
    "vgs_max": "V",
    "total_gate_charge_qg": "C",
    "gate_drain_charge_qgd": "C",
    "input_capacitance_ciss": "F",
    "output_capacitance_coss": "F",
    "max_junction_temp": "degC",
    "package": None,
    "thermal_resistance": "degC/W",
    "reverse_recovery_qrr": "C",
    "supply_voltage_min": "V",
    "supply_voltage_max": "V",
    "peak_source_current": "A",
    "peak_sink_current": "A",
    "input_logic_level": "V",
    "propagation_delay": "s",
    "rise_time": "s",
    "fall_time": "s",
    "uvlo_threshold": "V",
    "channel_count": None,
    "operating_temp_min": "degC",
    "operating_temp_max": "degC",
}

# --------------------------------------------------------------------------------------
# Vendor label -> standard name
# --------------------------------------------------------------------------------------

#: Exact (normalised) vendor labels. The key is the lower-cased label with the
#: whitespace collapsed.
ALIASES: dict[str, str] = {
    # --- DigiKey / Mouser MOSFET labels -------------------------------------------
    "drain to source voltage (vdss)": "vds_max",
    "drain source voltage (vdss)": "vds_max",
    "drain to source voltage vdss": "vds_max",
    "drain source voltage vdss": "vds_max",
    "drain-source voltage (vdss)": "vds_max",
    "drain to source voltage, vdss": "vds_max",
    "vds": "vds_max",
    "vdss": "vds_max",
    "continuous drain current (id)": "id_continuous",
    "continuous drain current (id) @ 25°c": "id_continuous",
    "continuous drain current id @ 25°c": "id_continuous",
    "continuous drain current (id) @ 25 c": "id_continuous",
    "continuous drain current (id) @ 100°c": "id_continuous",
    "current - continuous drain (id) @ 25°c": "id_continuous",
    "id": "id_continuous",
    "id continuous": "id_continuous",
    "rds(on) @ id, vgs": "rds_on",
    "rds(on) @ id, vgs, tj": "rds_on",
    "rds(on) @ id, vgs, 25°c": "rds_on",
    "rds(on)": "rds_on",
    "rds(on) max @ id, vgs": "rds_on",
    "rds (on) @ id, vgs": "rds_on",
    "rds on (max) @ id, vgs": "rds_on",
    "static drain to source on-resistance": "rds_on",
    "rds": "rds_on",
    "gate threshold voltage (vgs(th))": "vgs_threshold",
    "gate threshold voltage vgs(th)": "vgs_threshold",
    "gate threshold voltage": "vgs_threshold",
    "threshold voltage": "vgs_threshold",
    "vgs(th) (max) @ id": "vgs_threshold",
    "vgs(th)": "vgs_threshold",
    "vth": "vgs_threshold",
    "gate-source voltage (vgs)": "vgs_max",
    "gate to source voltage (vgs)": "vgs_max",
    "gate-source voltage": "vgs_max",
    "vgs max": "vgs_max",
    "vgs (max)": "vgs_max",
    "vgs": "vgs_max",
    "total gate charge (qg)": "total_gate_charge_qg",
    "total gate charge qg": "total_gate_charge_qg",
    "total gate charge": "total_gate_charge_qg",
    "gate charge (qg) (max) @ vgs": "total_gate_charge_qg",
    "qg": "total_gate_charge_qg",
    "gate to drain charge (qgd)": "gate_drain_charge_qgd",
    "gate-drain charge (qgd)": "gate_drain_charge_qgd",
    "gate to drain charge, qgd": "gate_drain_charge_qgd",
    "qgd": "gate_drain_charge_qgd",
    "input capacitance (ciss)": "input_capacitance_ciss",
    "input capacitance ciss": "input_capacitance_ciss",
    "input capacitance (ciss) (max) @ vds": "input_capacitance_ciss",
    "ciss": "input_capacitance_ciss",
    "output capacitance (coss)": "output_capacitance_coss",
    "output capacitance coss": "output_capacitance_coss",
    "output capacitance (coss) (max) @ vds": "output_capacitance_coss",
    "coss": "output_capacitance_coss",
    "operating junction temperature": "max_junction_temp",
    "maximum junction temperature": "max_junction_temp",
    "operating junction temperature range": "max_junction_temp",
    "junction temperature (tj)": "max_junction_temp",
    "max junction temp": "max_junction_temp",
    "package / case": "package",
    "package/case": "package",
    "supplier device package": "package",
    "package": "package",
    "thermal resistance - junction to case (rthjc)": "thermal_resistance",
    "thermal resistance junction to case (rthjc)": "thermal_resistance",
    "rthjc": "thermal_resistance",
    "junction to case thermal resistance": "thermal_resistance",
    "reverse recovery charge (qrr)": "reverse_recovery_qrr",
    "reverse recovery charge qrr": "reverse_recovery_qrr",
    "qrr": "reverse_recovery_qrr",
    # --- gate driver labels ------------------------------------------------------
    "supply voltage": "supply_voltage_max",
    "supply voltage (vcc)": "supply_voltage_max",
    "operating supply voltage": "supply_voltage_max",
    "vcc": "supply_voltage_max",
    "peak source current": "peak_source_current",
    "peak output current (io)": "peak_source_current",
    "output current": "peak_source_current",
    "peak sink current": "peak_sink_current",
    "peak output current": "peak_sink_current",
    "output current (sink)": "peak_sink_current",
    "input logic level": "input_logic_level",
    "input logic level (vil)": "input_logic_level",
    "input high level voltage": "input_logic_level",
    "vil": "input_logic_level",
    "propagation delay time": "propagation_delay",
    "propagation delay": "propagation_delay",
    "prop delay": "propagation_delay",
    "rise time": "rise_time",
    "fall time": "fall_time",
    "undervoltage lockout threshold": "uvlo_threshold",
    "uvlo threshold": "uvlo_threshold",
    "uvlo": "uvlo_threshold",
    "number of channels": "channel_count",
    "channel count": "channel_count",
    "channels": "channel_count",
    "number of drivers": "channel_count",
    "operating temperature range": "operating_temp_max",
    "operating temperature": "operating_temp_max",
    "operating temperature min": "operating_temp_min",
    "operating temperature max": "operating_temp_max",
    "ambient temperature range": "operating_temp_max",
}

#: Short names that Nexar reports in ``attribute.shortname``.
SHORTNAME_ALIASES: dict[str, str] = {
    "vds": "vds_max",
    "vdss": "vds_max",
    "id": "id_continuous",
    "rds": "rds_on",
    "rdson": "rds_on",
    "vth": "vgs_threshold",
    "vgst": "vgs_threshold",
    "vgs": "vgs_max",
    "qg": "total_gate_charge_qg",
    "qgd": "gate_drain_charge_qgd",
    "ciss": "input_capacitance_ciss",
    "coss": "output_capacitance_coss",
    "tjmax": "max_junction_temp",
    "rthjc": "thermal_resistance",
    "qrr": "reverse_recovery_qrr",
    "vcc": "supply_voltage_max",
    "isource": "peak_source_current",
    "isink": "peak_sink_current",
    "tpd": "propagation_delay",
    "tr": "rise_time",
    "tf": "fall_time",
    "uvlo": "uvlo_threshold",
}

#: Units that the distributors use and their canonical pint spelling.
UNIT_ALIASES: dict[str, str] = {
    "v": "V",
    "volt": "V",
    "volts": "V",
    "mv": "mV",
    "kv": "kV",
    "a": "A",
    "amp": "A",
    "amps": "A",
    "ampere": "A",
    "ma": "mA",
    "ua": "uA",
    "ohm": "ohm",
    "ohms": "ohm",
    "Ω": "ohm",
    "mohm": "mohm",
    "milliohm": "mohm",
    "milliohms": "mohm",
    "kohm": "kohm",
    "kΩ": "kohm",
    "uohm": "uohm",
    "µohm": "uohm",
    "nc": "nC",
    "nanocoulomb": "nC",
    "uc": "uC",
    "µc": "uC",
    "pc": "pC",
    "C": "degC",
    "c": "degC",
    "coulomb": "C",
    "pf": "pF",
    "nf": "nF",
    "uf": "uF",
    "µf": "uF",
    "f": "F",
    "farad": "F",
    "ns": "ns",
    "us": "us",
    "µs": "us",
    "ms": "ms",
    "s": "s",
    "sec": "s",
    "hz": "Hz",
    "khz": "kHz",
    "mhz": "MHz",
    "ghz": "GHz",
    "°c": "degC",
    "degc": "degC",
    "deg c": "degC",
    "degrees celsius": "degC",
    "°f": "degF",
    "w": "W",
    "mw": "mW",
    "uw": "uW",
    "j": "J",
    "rj": "degC/W",
    "degc/w": "degC/W",
    "°c/w": "degC/W",
    "kw": "kW",
    "K": "K",
    "k": "K",
}

#: Keys that may appear in a test condition.
CONDITION_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "ids",
        "idpk",
        "idpulse",
        "vgs",
        "vds",
        "vcc",
        "vin",
        "vout",
        "tc",
        "tj",
        "ta",
        "tl",
        "rl",
        "rg",
        "f",
        "m",
        "duty",
        "temperature",
        "temp",
    }
)

#: The spelling of a condition key in the stored value.
CONDITION_KEY_CANONICAL: dict[str, str] = {
    "id": "Id",
    "ids": "Ids",
    "idpk": "IdPk",
    "idpulse": "IdPulse",
    "vgs": "Vgs",
    "vds": "Vds",
    "vcc": "Vcc",
    "vin": "Vin",
    "vout": "Vout",
    "tc": "Tc",
    "tj": "Tj",
    "ta": "Ta",
    "tl": "Tl",
    "rl": "Rl",
    "rg": "Rg",
    "f": "f",
    "m": "m",
    "duty": "duty",
    "temperature": "temperature",
    "temp": "temperature",
}

_NUMBER_RE = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*)$")


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Return a lower-case slug that is safe for an id."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return slug.strip("-") or "part"


def canonical_unit(unit: str | None) -> str | None:
    """Return the canonical pint spelling of ``unit`` (or ``None``)."""
    if unit is None:
        return None
    key = unit.strip()
    if not key:
        return None
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    lowered = key.lower()
    if lowered in UNIT_ALIASES:
        return UNIT_ALIASES[lowered]
    return None


def _normalise_label(label: str) -> str:
    """Lower-case the label and collapse the whitespace."""
    text = label.replace("°", "°").strip().lower()
    return re.sub(r"\s+", " ", text)


def resolve_parameter_name(
    label: str | None,
    *,
    allow_fuzzy: bool = False,
    fuzzy_threshold: int = 95,
) -> str | None:
    """Return the standard name of a vendor label.

    ``None`` is returned for an unknown label - a value is never attached to a
    name that was only guessed.
    """
    if not label:
        return None
    key = _normalise_label(label)
    if not key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    short = re.sub(r"[^a-z0-9]", "", key)
    if short in SHORTNAME_ALIASES:
        return SHORTNAME_ALIASES[short]
    if not allow_fuzzy:
        return None
    best_score = 0
    best_name: str | None = None
    for alias, standard in ALIASES.items():
        score = fuzz.token_set_ratio(key, alias)
        if score > best_score:
            best_score = score
            best_name = standard
    if best_name is not None and best_score >= fuzzy_threshold:
        return best_name
    return None


def parse_value_with_unit(text: str | None) -> tuple[float | None, str | None]:
    """Split ``"12.0 mOhm"`` into ``(12.0, "mohm")``.

    ``(None, None)`` is returned when the text holds no number.
    """
    if text is None:
        return (None, None)
    if isinstance(text, (int, float)):
        return (float(text), None)
    cleaned = str(text).strip().replace(",", "").replace("±", "")
    if "@" in cleaned:
        cleaned = cleaned.split("@")[0].strip()
    if "(" in cleaned and ")" in cleaned:
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
    match = _NUMBER_RE.match(cleaned)
    if not match:
        return (None, None)
    number = float(match.group(1))
    unit = canonical_unit(match.group(2).strip())
    return (number, unit)


def parse_condition(label: str | None) -> dict[str, str]:
    """Return the test condition that a vendor label carries.

    ``"RDS(on) @ Id, Vgs"`` -> ``{"Id": "specified", "Vgs": "specified"}`` and
    ``"Continuous Drain Current (Id) @ 25°C"`` -> ``{"Tc": "25 C"}``.

    The condition travels with the value (FR-05). A condition without a known
    value is marked with ``"specified"`` - the number itself is only in the
    datasheet.
    """
    if not label:
        return {}
    text = str(label)
    if "@" not in text:
        return {}
    tail = text.split("@", 1)[1]
    condition: dict[str, str] = {}
    for token in re.split(r"[,;]", tail):
        item = token.strip()
        if not item:
            continue
        has_digit = any(ch.isdigit() for ch in item)
        cleaned = re.sub(r"[^A-Za-z0-9°/ ]", "", item).strip()
        cleaned = cleaned.replace("°C", " C").replace("°c", " C")
        if not cleaned:
            continue
        if not has_digit:
            key = cleaned.split()[0].lower()
            if key in CONDITION_KEYS:
                condition[CONDITION_KEY_CANONICAL.get(key, key)] = "specified"
            continue
        key = _condition_key_for_value(item)
        if key:
            condition[CONDITION_KEY_CANONICAL.get(key, key)] = cleaned
    return condition


def _condition_key_for_value(text: str) -> str | None:
    """Guess the condition key of a token that holds a value."""
    lowered = text.lower()
    if "°c" in lowered or "c)" in lowered or lowered.endswith(" c"):
        return "tc"
    for key in ("vgs", "vds", "vcc", "id", "tc", "tj", "ta", "f"):
        if lowered.startswith(key):
            return key
    return None


def infer_family(*texts: Any) -> str | None:
    """Return ``"mosfet"`` / ``"gate_driver"`` when the text makes it clear.

    ``None`` is returned when the family cannot be determined - the caller
    decides what to do then.
    """
    blob = " ".join(str(t) for t in texts if t).lower()
    if not blob:
        return None
    if "gate driver" in blob or "gate-driver" in blob or "gate_driver" in blob:
        return "gate_driver"
    if "mosfet" in blob or "fet," in blob or "fets" in blob:
        return "mosfet"
    if "transistor" in blob and "driver" not in blob:
        return "mosfet"
    return None
