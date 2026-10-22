"""Standard parameter names and the family schemas used by the LLM chains.

The frozen contract (:mod:`shared.schemas`) defines the *slots* of
:class:`~shared.schemas.MosfetSpec` and :class:`~shared.schemas.GateDriverSpec`.
The slot names are the standard parameter names used everywhere else in
PartPilot, so this module simply derives the allow-list from the contract and
adds a few local hints (the unit that a datasheet usually prints).

Nothing here is a contract change: it is a local adapter that keeps the chains
from hard-coding a list that would drift away from ``shared.schemas``.
"""

from __future__ import annotations

from shared.schemas import Family, GateDriverSpec, MosfetSpec, SpecValue

MOSFET_SPEC = MosfetSpec
GATE_DRIVER_SPEC = GateDriverSpec

MOSFET_PARAMETER_NAMES: tuple[str, ...] = tuple(MosfetSpec.model_fields)
GATE_DRIVER_PARAMETER_NAMES: tuple[str, ...] = tuple(GateDriverSpec.model_fields)
ALL_PARAMETER_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(MOSFET_PARAMETER_NAMES + GATE_DRIVER_PARAMETER_NAMES)
)

#: The unit a datasheet usually prints for a slot. The prompt asks the model to
#: report the unit *as printed*; the validator (WP5) converts it.
UNIT_HINTS: dict[str, str] = {
    "vds_max": "V",
    "id_continuous": "A",
    "rds_on": "mOhm (also printed as ohm)",
    "vgs_threshold": "V",
    "vgs_max": "V",
    "total_gate_charge_qg": "nC (also printed as uC)",
    "gate_drain_charge_qgd": "nC (also printed as uC)",
    "input_capacitance_ciss": "pF",
    "output_capacitance_coss": "pF",
    "max_junction_temp": "degC",
    "package": "package name (text, not a number)",
    "thermal_resistance": "degC/W",
    "reverse_recovery_qrr": "nC",
    "supply_voltage_min": "V",
    "supply_voltage_max": "V",
    "peak_source_current": "A",
    "peak_sink_current": "A",
    "input_logic_level": "V",
    "propagation_delay": "ns",
    "rise_time": "ns",
    "fall_time": "ns",
    "uvlo_threshold": "V",
    "channel_count": "count (text, not a number)",
    "operating_temp_min": "degC",
    "operating_temp_max": "degC",
}


def spec_model_for(family: Family) -> type:
    """Return the structured-output target for ``family``."""
    if family == Family.GATE_DRIVER:
        return GATE_DRIVER_SPEC
    return MOSFET_SPEC


def parameter_names_for(family: Family) -> tuple[str, ...]:
    """Return the standard parameter names that are allowed for ``family``."""
    if family == Family.GATE_DRIVER:
        return GATE_DRIVER_PARAMETER_NAMES
    return MOSFET_PARAMETER_NAMES


def is_known_parameter(name: str, family: Family | None = None) -> bool:
    """Return ``True`` when ``name`` is a standard parameter name."""
    if family is None:
        return name in ALL_PARAMETER_NAMES
    return name in parameter_names_for(family)


def unit_hint(name: str) -> str:
    """Return the unit hint for a standard parameter name."""
    return UNIT_HINTS.get(name, "SI unit as printed in the source")


def describe_spec_schema(model: type) -> str:
    """Return a compact, human readable description of a spec schema.

    The full JSON schema is too noisy for a prompt; the model only needs the
    slot names and the shape of one slot.
    """
    lines = [f"Output schema: {model.__name__}"]
    lines.append("Every slot below is either null or an object with these keys:")
    for key, field in SpecValue.model_fields.items():
        annotation = getattr(field.annotation, "__name__", str(field.annotation))
        lines.append(f"  - {key}: {annotation}")
    lines.append("Slots of the schema:")
    for name in model.model_fields:
        lines.append(f"  - {name} (typical unit: {unit_hint(name)})")
    return "\n".join(lines)


__all__ = [
    "ALL_PARAMETER_NAMES",
    "GATE_DRIVER_PARAMETER_NAMES",
    "GATE_DRIVER_SPEC",
    "MOSFET_PARAMETER_NAMES",
    "MOSFET_SPEC",
    "UNIT_HINTS",
    "describe_spec_schema",
    "is_known_parameter",
    "parameter_names_for",
    "spec_model_for",
    "unit_hint",
]
