"""Unit normalisation for PartPilot (FR-06, plan WP5 step 1).

Every value that enters the database is expressed in a canonical SI unit.  This
module owns the mapping from a datasheet unit spelling to that canonical unit.

Design rules
------------
* There is exactly **one** :class:`pint.UnitRegistry` in the process
  (``ureg``).  Creating a registry per call is slow and makes unit objects
  incomparable, so it must never happen.
* An unknown or unparseable unit never raises.  ``normalize`` returns
  ``(None, None)`` and the caller (the validator) marks the value for review.
* A unit *mismatch* (a voltage where a current is expected) is not an error
  here - it is detected by the field rule in :mod:`validation.rules`.

Canonical units
---------------
============== =======
dimension     unit
============== =======
voltage       ``V``
current       ``A``
resistance    ``ohm``
capacitance   ``F``
charge        ``C``
time          ``s``
temperature   ``degC``
thermal res.  ``degC/W``
dimensionless ``None``
============== =======
"""

from __future__ import annotations

import re
from typing import Final

import pint

__all__ = [
    "CANONICAL_UNITS",
    "PARAMETER_UNITS",
    "canonical_unit_for",
    "clean_unit",
    "is_known_unit",
    "normalize",
    "ureg",
]

#: The one and only unit registry of this process.
ureg: Final[pint.UnitRegistry] = pint.UnitRegistry()

#: Canonical unit per physical dimension.
CANONICAL_UNITS: Final[dict[str, str]] = {
    "voltage": "V",
    "current": "A",
    "resistance": "ohm",
    "capacitance": "F",
    "charge": "C",
    "time": "s",
    "temperature": "degC",
    "thermal_resistance": "degC/W",
    "dimensionless": "",
}

#: The canonical unit expected for every standard parameter name (plan 7.1).
PARAMETER_UNITS: Final[dict[str, str | None]] = {
    # MOSFET
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
    "thermal_resistance": "degC/W",
    "reverse_recovery_qrr": "C",
    "package": None,
    # Gate driver
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

#: Units that pint cannot disambiguate on its own, or that are spelled
#: differently in datasheets.  Keys are the cleaned (lower case) spelling.
_UNIT_ALIASES: Final[dict[str, str]] = {
    # "C" is a coulomb in pint; a datasheet that writes "C" for a temperature
    # is resolved by the caller through the ``expected_unit`` hint.
    "c": "C",
    "coulomb": "C",
    "coulombs": "C",
    "celsius": "degC",
    "degree celsius": "degC",
    "degrees celsius": "degC",
    "deg c": "degC",
    "k": "K",
    "kelvin": "K",
    "kelvins": "K",
    # Thermal resistance: datasheets write "C/W", pint reads that as coulomb
    # per watt.  It always means degrees Celsius per watt.
    "c/w": "degC/W",
    "k/w": "degC/W",
    "degc/w": "degC/W",
    "celsius/w": "degC/W",
    # Long spellings that pint does not know.
    "volt": "V",
    "volts": "V",
    "millivolt": "mV",
    "amp": "A",
    "amps": "A",
    "ampere": "A",
    "amperes": "A",
    "milliamp": "mA",
    "milliampere": "mA",
    "ohm": "ohm",
    "ohms": "ohm",
    "milliohm": "mohm",
    "milliohms": "mohm",
    "microohm": "uohm",
    "microohms": "uohm",
    "kilohm": "kohm",
    "kilohms": "kohm",
    "farad": "F",
    "farads": "F",
    "picofarad": "pF",
    "nanofarad": "nF",
    "microfarad": "uF",
    "millifarad": "mF",
    "nanocoulomb": "nC",
    "microcoulomb": "uC",
    "millicoulomb": "mC",
    "second": "s",
    "seconds": "s",
    "sec": "s",
    "millisecond": "ms",
    "milliseconds": "ms",
    "microsecond": "us",
    "microseconds": "us",
    "nanosecond": "ns",
    "nanoseconds": "ns",
    "picosecond": "ps",
    "watt": "W",
    "watts": "W",
}

#: Spellings that mean "temperature *difference*" rather than an absolute
#: temperature.  A difference of 1 K is a difference of 1 degC, so the
#: magnitude is kept as it is.
_DELTA_TEMPERATURE_SPELLINGS: Final[frozenset[str]] = frozenset(
    {
        "k",
        "kelvin",
        "kelvins",
        "mk",
        "mkelvin",
        "delta degc",
        "delta_degc",
        "delta deg c",
        "delta_degree_celsius",
        "degk",
    }
)

#: Candidate canonical units, tried in this order.  The order matters: a
#: thermal resistance (degC/W) must be tested before a plain temperature.
_TARGETS: Final[tuple[str, ...]] = ("degC/W", "V", "A", "ohm", "F", "C", "s", "degC")

_SPACE_AROUND_SLASH = re.compile(r"\s*/\s*")
_WHITESPACE = re.compile(r"\s+")
_DEG_SPACE = re.compile(r"\bdeg\s+")


def clean_unit(unit: str | None) -> str | None:
    """Return a cleaned unit spelling, or ``None`` for an empty unit.

    The micro sign (``µ``/``μ``) and the degree sign (``°``) are folded to
    their ASCII equivalents so that ``µF`` and ``uF`` behave the same.
    """
    if unit is None:
        return None
    text = str(unit).strip()
    if not text:
        return None
    text = text.replace("µ", "u").replace("μ", "u").replace("°", "deg")
    text = _SPACE_AROUND_SLASH.sub("/", text)
    text = _DEG_SPACE.sub("deg", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text or None


def _spec_for(cleaned: str, expected_unit: str | None) -> str | None:
    """Return the pint unit string to use, or ``None`` when it is unknown."""
    key = cleaned.lower()
    if key == "c" and expected_unit == "degC":
        # Ambiguous spelling: the field expects a temperature, so "C" is
        # degrees Celsius here (and not a coulomb).
        return "degC"
    return _UNIT_ALIASES.get(key, cleaned)


def _is_delta_temperature(spec: str) -> bool:
    return spec.lower() in _DELTA_TEMPERATURE_SPELLINGS


def is_known_unit(unit: str | None) -> bool:
    """Return ``True`` when ``unit`` can be parsed by pint."""
    cleaned = clean_unit(unit)
    if cleaned is None:
        return False
    spec = _spec_for(cleaned, None)
    try:
        ureg.Quantity(0.0, spec)
    except Exception:
        return False
    return True


def normalize(
    value: float | None,
    unit: str | None,
    *,
    expected_unit: str | None = None,
) -> tuple[float | None, str | None]:
    """Convert ``value`` to the canonical unit of its dimension.

    Parameters
    ----------
    value:
        The numeric value.  ``None`` returns ``(None, None)``.
    unit:
        The unit as written in the datasheet.  ``None`` or an empty string
        means "dimensionless" and returns ``(value, None)``.
    expected_unit:
        Optional hint (the canonical unit of the field).  It only resolves the
        ambiguous spelling ``C`` (coulomb vs. degrees Celsius).

    Returns
    -------
    tuple
        ``(value, canonical_unit)``.  ``(None, None)`` is returned when the
        unit cannot be parsed - the caller must not raise in that case.
    """
    if value is None:
        return (None, None)
    try:
        magnitude = float(value)
    except (TypeError, ValueError):
        return (None, None)

    cleaned = clean_unit(unit)
    if cleaned is None:
        # No unit at all: the value is dimensionless.
        return (magnitude, None)

    spec = _spec_for(cleaned, expected_unit)
    try:
        quantity = ureg.Quantity(magnitude, spec)
    except Exception:
        return (None, None)

    try:
        if quantity.dimensionless:
            return (magnitude, None)
    except Exception:
        return (None, None)

    if _is_delta_temperature(spec):
        try:
            return (float(quantity.to("delta_degC").magnitude), "degC")
        except Exception:
            return (None, None)

    for target in _TARGETS:
        try:
            converted = quantity.to(target)
        except Exception:
            continue
        try:
            return (float(converted.magnitude), target)
        except Exception:
            return (None, None)
    return (None, None)


def canonical_unit_for(name: str) -> str | None:
    """Return the canonical unit expected for a standard parameter name.

    ``None`` is returned for an unknown name and for a non-numeric field such
    as ``package``.
    """
    if not name:
        return None
    return PARAMETER_UNITS.get(str(name).strip().lower())
