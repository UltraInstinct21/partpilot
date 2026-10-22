"""Per-field range rules and API tolerances (plan WP5 steps 2 and 4).

The table below is the *only* place where the allowed range of a standard
parameter is defined.  The bounds are stored in the **canonical** unit of the
field (see :mod:`validation.units`), the comment states the range in the unit
a human reads in a datasheet.

A value outside its range is **rejected** (FR-07).  A name that is not in the
table has no range rule - it is never rejected for being out of range, because
an unknown field must not silently disappear (plan WP5, "stop wrong values from
reaching the database" applies to the *known* fields).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "DEFAULT_ABS_FLOOR",
    "DEFAULT_REL_TOLERANCE",
    "FIELD_RULES",
    "FieldRule",
    "rule_for",
    "tolerance_for",
    "values_agree",
]

#: Default relative tolerance for the API cross check (5 %).
DEFAULT_REL_TOLERANCE: Final[float] = 0.05

#: Default absolute floor for the API cross check.  It keeps tiny values from
#: being reported as a disagreement because of floating point noise only.
DEFAULT_ABS_FLOOR: Final[float] = 1e-9


@dataclass(frozen=True)
class FieldRule:
    """The allowed range of one standard parameter.

    Attributes
    ----------
    name:
        Standard parameter name (plan 7.1).
    unit:
        Canonical unit of the field, ``None`` for a dimensionless or
        non-numeric field.
    minimum / maximum:
        Allowed range **in the canonical unit**, inclusive.
    rel_tolerance:
        Relative tolerance used when the value is compared with the API
        value (FR-08).
    abs_floor:
        Absolute floor of that comparison, in the canonical unit.
    integer:
        ``True`` when the value must be a whole number (e.g. ``channel_count``).
    note:
        Why the bounds are what they are.
    """

    name: str
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    rel_tolerance: float = DEFAULT_REL_TOLERANCE
    abs_floor: float = DEFAULT_ABS_FLOOR
    integer: bool = False
    note: str = ""

    @property
    def has_range(self) -> bool:
        """``True`` when the field carries a numeric range rule."""
        return self.minimum is not None or self.maximum is not None

    def in_range(self, magnitude: float) -> bool:
        """Return ``True`` when ``magnitude`` is inside the allowed range."""
        if self.minimum is not None and magnitude < self.minimum:
            return False
        if self.maximum is not None and magnitude > self.maximum:
            return False
        return True

    def is_integer(self, magnitude: float) -> bool:
        """Return ``True`` when ``magnitude`` is a whole number."""
        if not self.integer:
            return True
        return abs(magnitude - round(magnitude)) < 1e-9


def _rule(
    name: str,
    unit: str | None,
    minimum: float | None,
    maximum: float | None,
    note: str,
    *,
    rel_tolerance: float = DEFAULT_REL_TOLERANCE,
    abs_floor: float = DEFAULT_ABS_FLOOR,
    integer: bool = False,
) -> FieldRule:
    return FieldRule(
        name=name,
        unit=unit,
        minimum=minimum,
        maximum=maximum,
        rel_tolerance=rel_tolerance,
        abs_floor=abs_floor,
        integer=integer,
        note=note,
    )


#: The range table.  Bounds are in the canonical unit; the note repeats them
#: in the unit used in the datasheet.
FIELD_RULES: Final[dict[str, FieldRule]] = {
    rule.name: rule
    for rule in (
        # ---------------------------------------------------------------- MOSFET
        _rule(
            "vds_max",
            "V",
            1.0,
            2000.0,
            "Drain-source voltage rating: 1 V for logic level devices, "
            "2000 V for the highest voltage SiC MOSFETs.",
        ),
        _rule(
            "id_continuous",
            "A",
            0.01,
            1000.0,
            "Continuous drain current: 0.01 A for a small SOT-23 device, "
            "1000 A for a automotive module.",
        ),
        _rule(
            "rds_on",
            "ohm",
            0.0001,
            100.0,
            "On-state resistance: 100 uohm for a top class part, 100 ohm for "
            "a linear/high voltage device.  Datasheets usually write mohm.",
            abs_floor=1e-6,
        ),
        _rule(
            "vgs_threshold",
            "V",
            0.1,
            5.0,
            "Gate threshold voltage: 0.1 V for a logic level device, 5 V for "
            "a classic high voltage device.",
        ),
        _rule(
            "vgs_max",
            "V",
            1.0,
            50.0,
            "Maximum gate-source voltage: 1 V for a low voltage device, "
            "50 V for a +/- 25 V rated driver MOSFET.",
        ),
        _rule(
            "total_gate_charge_qg",
            "C",
            0.01e-9,
            2000e-9,
            "Total gate charge: 0.01 nC for a tiny device, 2000 nC for a big " "automotive MOSFET.",
            abs_floor=1e-12,
        ),
        _rule(
            "gate_drain_charge_qgd",
            "C",
            0.01e-9,
            1000e-9,
            "Gate-drain charge (Miller charge): 0.01 nC .. 1000 nC.",
            abs_floor=1e-12,
        ),
        _rule(
            "input_capacitance_ciss",
            "F",
            1e-12,
            100000e-12,
            "Input capacitance: 1 pF .. 100000 pF (100 nF).",
            rel_tolerance=0.10,
            abs_floor=1e-15,
        ),
        _rule(
            "output_capacitance_coss",
            "F",
            1e-12,
            100000e-12,
            "Output capacitance: 1 pF .. 100000 pF (100 nF).",
            rel_tolerance=0.10,
            abs_floor=1e-15,
        ),
        _rule(
            "max_junction_temp",
            "degC",
            25.0,
            300.0,
            "Maximum junction temperature: 25 degC (industrial low) .. " "300 degC (SiC).",
        ),
        _rule(
            "thermal_resistance",
            "degC/W",
            0.01,
            200.0,
            "Thermal resistance junction to case: 0.01 degC/W (a big module) "
            ".. 200 degC/W (a small SOT-23).",
        ),
        _rule(
            "reverse_recovery_qrr",
            "C",
            0.1e-9,
            100000e-9,
            "Reverse recovery charge: 0.1 nC .. 100000 nC (100 uC).",
            abs_floor=1e-12,
        ),
        _rule(
            "package",
            None,
            None,
            None,
            "Package is a text field, it is never range checked.",
        ),
        # ----------------------------------------------------------- GATE DRIVER
        _rule(
            "supply_voltage_min",
            "V",
            0.5,
            100.0,
            "Minimum supply voltage: 0.5 V (a low voltage CMOS driver) .. "
            "100 V (a high side driver).",
        ),
        _rule(
            "supply_voltage_max",
            "V",
            1.0,
            200.0,
            "Maximum supply voltage: 1 V .. 200 V (a 150 V bootstrap driver).",
        ),
        _rule(
            "peak_source_current",
            "A",
            0.05,
            200.0,
            "Peak source (pull-up) current: 0.05 A .. 200 A.",
        ),
        _rule(
            "peak_sink_current",
            "A",
            0.05,
            200.0,
            "Peak sink (pull-down) current: 0.05 A .. 200 A.",
        ),
        _rule(
            "input_logic_level",
            "V",
            0.0,
            10.0,
            "Input logic threshold: 0 V .. 10 V (a 5 V or 3.3 V CMOS driver).",
        ),
        _rule(
            "propagation_delay",
            "s",
            1e-9,
            100000e-9,
            "Propagation delay: 1 ns .. 100 us.",
            abs_floor=1e-12,
        ),
        _rule(
            "rise_time",
            "s",
            1e-9,
            100000e-9,
            "Rise time: 1 ns .. 100 us.",
            abs_floor=1e-12,
        ),
        _rule(
            "fall_time",
            "s",
            1e-9,
            100000e-9,
            "Fall time: 1 ns .. 100 us.",
            abs_floor=1e-12,
        ),
        _rule(
            "uvlo_threshold",
            "V",
            0.5,
            100.0,
            "Undervoltage lockout threshold: 0.5 V .. 100 V.",
        ),
        _rule(
            "channel_count",
            None,
            1.0,
            8.0,
            "Number of driver channels: 1 .. 8, a whole number.",
            integer=True,
            abs_floor=1e-9,
        ),
        _rule(
            "operating_temp_min",
            "degC",
            -100.0,
            25.0,
            "Minimum operating (ambient) temperature: -100 degC .. 25 degC.",
        ),
        _rule(
            "operating_temp_max",
            "degC",
            40.0,
            300.0,
            "Maximum operating (ambient) temperature: 40 degC .. 300 degC.",
        ),
    )
}


def rule_for(name: str | None) -> FieldRule | None:
    """Return the rule of a standard parameter name, or ``None``."""
    if not name:
        return None
    return FIELD_RULES.get(str(name).strip().lower())


def tolerance_for(name: str | None) -> tuple[float, float]:
    """Return ``(relative_tolerance, absolute_floor)`` for a field."""
    rule = rule_for(name)
    if rule is None:
        return (DEFAULT_REL_TOLERANCE, DEFAULT_ABS_FLOOR)
    return (rule.rel_tolerance, rule.abs_floor)


def values_agree(
    value: float,
    other: float,
    rel_tolerance: float = DEFAULT_REL_TOLERANCE,
    abs_floor: float = DEFAULT_ABS_FLOOR,
) -> bool:
    """Return ``True`` when two values agree within the tolerance.

    The comparison is symmetric and uses the larger magnitude as the
    reference.  ``abs_floor`` keeps very small values from being reported as
    a disagreement when the difference is only floating point noise.
    """
    try:
        value = float(value)
        other = float(other)
    except (TypeError, ValueError):
        return False
    if value != value or other != other:  # NaN
        return False
    difference = abs(value - other)
    reference = max(abs(value), abs(other))
    allowed = rel_tolerance * reference + abs_floor
    return difference <= allowed


def relative_difference(value: float, other: float) -> float:
    """Return the relative difference of two values (``0.0`` when equal)."""
    value = float(value)
    other = float(other)
    reference = max(abs(value), abs(other))
    if reference == 0:
        return 0.0
    return abs(value - other) / reference
