"""Private unit helper for the data layer (agent E-data).

Why this module exists
----------------------
``shared.schemas`` states that every stored value carries a **canonical pint
unit** (``"V"``, ``"A"``, ``"ohm"``, ``"degC"`` ...).  The validator agent (D)
owns the canonical unit policy for extracted values, but no agent may import
another agent's package (``docs/CONTRACTS.md``).  The small amount of unit
logic that the *repository* needs is therefore re-implemented here.

What the repository needs the units for
---------------------------------------
* ``SearchFilter`` carries ``ParameterConstraint`` values in whatever unit the
  user asked for (``5 mohm``).  The stored ``parameters.value`` is canonical
  (``0.005 ohm``).  The comparison has to happen in one single space, so the
  constraint is converted to the canonical unit before it reaches SQL.
* Values that were written by another agent (or by hand) may still carry a
  scaled unit.  The SQL expression that compares them therefore scales the
  stored value into the canonical unit with a ``CASE`` expression, so the
  comparison is correct either way.

Canonical units
---------------
=========  ===========
dimension  canonical
=========  ===========
voltage    ``V``
current    ``A``
resistance ``ohm``
charge     ``C``
capacitance ``F``
time       ``s``
power      ``W``
frequency  ``Hz``
temperature ``degC``
thermal resistance ``degC/W``
=========  ===========

``K`` is deliberately *not* part of the table: ``K`` and ``degC`` share the
``[temperature]`` dimension and pint would turn ``300 K`` into ``26.85 degC``
(an absolute conversion), which is not what a stored value means.
"""

from __future__ import annotations

from typing import Any

import pint

__all__ = [
    "PARAMETER_UNITS",
    "canonical_unit",
    "canonicalize",
    "is_known_unit",
    "unit_scale_map",
]

_ureg = pint.UnitRegistry()

#: canonical unit per physical dimension (first match wins).
_CANONICAL_BY_DIMENSION: list[tuple[Any, str]] = [
    (_ureg.V.dimensionality, "V"),
    (_ureg.A.dimensionality, "A"),
    (_ureg.ohm.dimensionality, "ohm"),
    (_ureg.F.dimensionality, "F"),
    (_ureg.C.dimensionality, "C"),
    (_ureg.s.dimensionality, "s"),
    (_ureg.W.dimensionality, "W"),
    (_ureg.Hz.dimensionality, "Hz"),
    (_ureg.degC.dimensionality, "degC"),
    ((_ureg.degC / _ureg.W).dimensionality, "degC/W"),
    ((_ureg.A / _ureg.V).dimensionality, "A/V"),
]

#: units the data layer knows how to scale.  Every other unit is passed
#: through unchanged (it is assumed to be canonical already).
_KNOWN_UNITS: tuple[str, ...] = (
    # voltage
    "V",
    "mV",
    "uV",
    "kV",
    # current
    "A",
    "mA",
    "uA",
    "nA",
    "kA",
    # resistance
    "ohm",
    "mohm",
    "kohm",
    "uohm",
    # capacitance
    "F",
    "mF",
    "uF",
    "nF",
    "pF",
    # charge
    "C",
    "mC",
    "uC",
    "nC",
    "pC",
    # time
    "s",
    "ms",
    "us",
    "ns",
    "ps",
    # power
    "W",
    "mW",
    "uW",
    "kW",
    # frequency
    "Hz",
    "kHz",
    "MHz",
    "GHz",
    # temperature (absolute offset unit, scale is 1)
    "degC",
    # derived
    "degC/W",
    "A/V",
)

#: canonical unit of every standard parameter name of the frozen spec models
#: (``shared.schemas.MosfetSpec`` / ``GateDriverSpec``).  Used when a
#: ``ParameterConstraint`` does not carry a unit: the constraint numbers are
#: then assumed to be canonical already.
PARAMETER_UNITS: dict[str, str] = {
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
    # gate driver
    "supply_voltage_min": "V",
    "supply_voltage_max": "V",
    "peak_source_current": "A",
    "peak_sink_current": "A",
    "input_logic_level": "V",
    "propagation_delay": "s",
    "rise_time": "s",
    "fall_time": "s",
    "uvlo_threshold": "V",
    "operating_temp_min": "degC",
    "operating_temp_max": "degC",
}


def canonical_unit(unit: str | None) -> str | None:
    """Return the canonical unit of ``unit`` or ``None`` when it is unknown.

    ``None`` means "this unit cannot be converted", the caller then has to keep
    the value and the unit as they are.
    """
    if not unit:
        return None
    try:
        quantity = _ureg.Quantity(1.0, unit)
    except Exception:  # pragma: no cover - pint raises many different types
        return None
    dimensionality = quantity.dimensionality
    for known, target in _CANONICAL_BY_DIMENSION:
        if dimensionality == known:
            return target
    return None


def canonicalize(value: float | None, unit: str | None) -> tuple[float | None, str | None]:
    """Return ``(value, canonical_unit)`` for ``value`` expressed in ``unit``.

    The value is unchanged when it is ``None``, when there is no unit or when
    the unit cannot be converted (e.g. an unknown dimension).
    """
    if value is None or not unit:
        return value, unit
    target = canonical_unit(unit)
    if target is None or target == unit:
        return value, unit
    try:
        converted = _ureg.Quantity(value, unit).to(target)
    except Exception:
        # offset units inside compound expressions cannot be converted by pint
        return value, unit
    return float(converted.magnitude), target


def is_known_unit(unit: str | None) -> bool:
    """Return ``True`` when the data layer can scale ``unit``."""
    return bool(unit) and unit in _KNOWN_UNITS


def unit_scale_map() -> dict[str, float]:
    """Return ``{unit: factor}`` that converts a value into its canonical unit.

    Only units with a factor different from ``1.0`` are needed by the SQL
    ``CASE`` expression, but the full map is returned so that callers can
    reason about it.
    """
    scales: dict[str, float] = {}
    for unit in _KNOWN_UNITS:
        converted, target = canonicalize(1.0, unit)
        if converted is None or target is None:
            continue
        scales[unit] = float(converted)
    return scales
