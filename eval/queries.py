"""The 30 natural-language search queries of plan WP6 and WP8.

The plan asks for 30 test queries. The filter builder must give the correct
filter in at least 80 % of the cases.

Every entry is a ``(query, expected_filter)`` pair. The expected filter uses
the field names of ``SearchFilter`` in ``backend/shared/schemas.py``:

``family``, ``manufacturer``, ``manufacturer_in``, ``mpn_contains``,
``package``, ``package_in``, ``lifecycle_status``, ``in_stock``,
``parameters`` and ``text``.

A ``parameters`` entry is a list of dictionaries with the keys ``name`` and
one or more of ``min``, ``max`` and ``typ``. The unit is not compared, because
a correct filter may use the canonical unit or the unit of the datasheet.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "EXPECTED_FILTER_KEYS",
    "QUERIES",
    "QUERY_COUNT",
    "validate_queries",
]

#: The keys that an expected filter may hold.
EXPECTED_FILTER_KEYS = frozenset(
    {
        "family",
        "manufacturer",
        "manufacturer_in",
        "mpn_contains",
        "package",
        "package_in",
        "lifecycle_status",
        "in_stock",
        "parameters",
        "text",
    }
)

#: The 30 test queries.
QUERIES: list[tuple[str, dict[str, Any]]] = [
    (
        "100 V N-channel MOSFET with Rds(on) below 5 mOhm, in stock",
        {
            "family": "mosfet",
            "in_stock": True,
            "parameters": [{"name": "rds_on", "unit": "mohm", "max": 5.0}],
        },
    ),
    (
        "Infineon MOSFET with Rds(on) under 10 mOhm",
        {
            "family": "mosfet",
            "manufacturer": "Infineon Technologies",
            "parameters": [{"name": "rds_on", "unit": "mohm", "max": 10.0}],
        },
    ),
    (
        "gate driver for a 12 V supply",
        {
            "family": "gate_driver",
            "parameters": [{"name": "supply_voltage_max", "unit": "V", "min": 12.0}],
        },
    ),
    (
        "gate driver with 4 A peak source current",
        {
            "family": "gate_driver",
            "parameters": [{"name": "peak_source_current", "unit": "A", "min": 4.0}],
        },
    ),
    ("TO-220 power MOSFET", {"family": "mosfet", "package": "TO-220"}),
    ("SO-8 power MOSFET", {"family": "mosfet", "package": "SO-8"}),
    ("active parts from onsemi", {"manufacturer": "onsemi", "lifecycle_status": ["active"]}),
    ("obsolete parts", {"lifecycle_status": ["obsolete"]}),
    ("NRND parts that are in stock", {"lifecycle_status": ["nrnd"], "in_stock": True}),
    (
        "trench MOSFET below 60 V with a very low Rds(on)",
        {
            "family": "mosfet",
            "parameters": [
                {"name": "vds_max", "unit": "V", "max": 60.0},
                {"name": "rds_on", "unit": "mohm", "max": 3.0},
            ],
        },
    ),
    (
        "MOSFET with 10 A continuous drain current",
        {
            "family": "mosfet",
            "parameters": [{"name": "id_continuous", "unit": "A", "min": 10.0}],
        },
    ),
    (
        "30 V MOSFET for a 3 A load",
        {
            "family": "mosfet",
            "parameters": [
                {"name": "vds_max", "unit": "V", "min": 30.0},
                {"name": "id_continuous", "unit": "A", "min": 3.0},
            ],
        },
    ),
    (
        "gate driver with a propagation delay below 100 ns",
        {
            "family": "gate_driver",
            "parameters": [{"name": "propagation_delay", "unit": "ns", "max": 100.0}],
        },
    ),
    (
        "gate driver with an undervoltage lockout",
        {
            "family": "gate_driver",
            "parameters": [{"name": "uvlo_threshold", "unit": "V", "min": 1.0}],
        },
    ),
    (
        "dual channel gate driver",
        {"family": "gate_driver", "parameters": [{"name": "channel_count", "typ": 2.0}]},
    ),
    (
        "gate driver with 5 A peak sink current",
        {
            "family": "gate_driver",
            "parameters": [{"name": "peak_sink_current", "unit": "A", "min": 5.0}],
        },
    ),
    ("Vishay Si7148DP", {"mpn_contains": "Si7148DP"}),
    ("parts in the DQG package", {"package": "DQG"}),
    (
        "MOSFET with a low total gate charge",
        {
            "family": "mosfet",
            "parameters": [{"name": "total_gate_charge_qg", "unit": "nC", "max": 50.0}],
        },
    ),
    (
        "MOSFET with a 175 C maximum junction temperature",
        {
            "family": "mosfet",
            "parameters": [{"name": "max_junction_temp", "unit": "degC", "min": 175.0}],
        },
    ),
    ("STMicroelectronics power MOSFET", {"family": "mosfet", "manufacturer": "STMicroelectronics"}),
    (
        "Nexperia MOSFET below 100 V",
        {
            "family": "mosfet",
            "manufacturer": "Nexperia",
            "parameters": [{"name": "vds_max", "unit": "V", "max": 100.0}],
        },
    ),
    (
        "gate driver that works from 4.5 V up to 18 V",
        {
            "family": "gate_driver",
            "parameters": [
                {"name": "supply_voltage_min", "unit": "V", "max": 4.5},
                {"name": "supply_voltage_max", "unit": "V", "min": 18.0},
            ],
        },
    ),
    (
        "gate driver with a 20 ns rise time",
        {"family": "gate_driver", "parameters": [{"name": "rise_time", "unit": "ns", "max": 20.0}]},
    ),
    (
        "in-stock MOSFETs from Infineon",
        {"family": "mosfet", "manufacturer": "Infineon Technologies", "in_stock": True},
    ),
    (
        "MOSFET with a 200 V drain source voltage",
        {"family": "mosfet", "parameters": [{"name": "vds_max", "unit": "V", "min": 200.0}]},
    ),
    (
        "gate driver with a 3.3 V input logic level",
        {
            "family": "gate_driver",
            "parameters": [{"name": "input_logic_level", "unit": "V", "typ": 3.3}],
        },
    ),
    (
        "parts from Infineon or Nexperia",
        {"manufacturer_in": ["Infineon Technologies", "Nexperia"]},
    ),
    (
        "MOSFET with a gate drain charge below 10 nC",
        {
            "family": "mosfet",
            "parameters": [{"name": "gate_drain_charge_qgd", "unit": "nC", "max": 10.0}],
        },
    ),
    ("gate drivers in the SO-8 package", {"family": "gate_driver", "package": "SO-8"}),
]

#: The number of test queries that the plan asks for.
QUERY_COUNT = 30


def validate_queries(queries: list[tuple[str, dict[str, Any]]] | None = None) -> list[str]:
    """Check the query list and return the list of problems.

    An empty list means that the query list is valid.
    """
    items = QUERIES if queries is None else queries
    problems: list[str] = []
    seen: set[str] = set()
    for number, item in enumerate(items, start=1):
        if not isinstance(item, tuple) or len(item) != 2:
            problems.append(f"query {number}: the entry must be a (query, expected_filter) tuple")
            continue
        query, expected = item
        if not str(query).strip():
            problems.append(f"query {number}: the query text is empty")
        if str(query) in seen:
            problems.append(f"query {number}: the query text {query!r} is used twice")
        seen.add(str(query))
        if not isinstance(expected, dict) or not expected:
            problems.append(f"query {number}: the expected filter must be a non empty dictionary")
            continue
        for key in expected:
            if key not in EXPECTED_FILTER_KEYS:
                problems.append(
                    f"query {number}: the filter key {key!r} is not a SearchFilter field"
                )
        constraints = expected.get("parameters")
        if constraints is not None:
            if not isinstance(constraints, list) or not constraints:
                problems.append(f"query {number}: the parameters must be a non empty list")
                continue
            for constraint in constraints:
                if not isinstance(constraint, dict) or not constraint.get("name"):
                    problems.append(f"query {number}: a constraint has no name")
                    continue
                bounds = [key for key in ("min", "max", "typ") if constraint.get(key) is not None]
                if not bounds:
                    problems.append(
                        f"query {number}: the constraint {constraint.get('name')!r} has no min, max or typ"
                    )
    if queries is None and len(items) != QUERY_COUNT:
        problems.append(
            f"the query list holds {len(items)} queries, the plan asks for {QUERY_COUNT}"
        )
    return problems
