"""The ``name_map`` repository (raw table header -> standard name)."""

from __future__ import annotations


def test_lookup_of_an_unknown_name_is_none(name_map) -> None:
    assert name_map.lookup("Nothing", "mosfet") is None


def test_add_and_lookup(name_map) -> None:
    name_map.add("Drain to Source Voltage (Vdss)", "vds_max", "mosfet", approved=True)
    assert name_map.lookup("Drain to Source Voltage (Vdss)", "mosfet") == "vds_max"


def test_add_is_idempotent(name_map) -> None:
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=True)
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=True)
    assert len(name_map.all_mappings()) == 1


def test_all_mappings_can_be_filtered_by_family(name_map) -> None:
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=True)
    name_map.add("Propagation Delay", "propagation_delay", "gate_driver", approved=True)
    name_map.add("Something", "something", None, approved=False)

    assert len(name_map.all_mappings()) == 3
    assert len(name_map.all_mappings("mosfet")) == 1
    assert name_map.all_mappings("mosfet")[0]["standard_name"] == "total_gate_charge_qg"
    assert len(name_map.all_mappings("gate_driver")) == 1


def test_a_family_mapping_wins_over_a_global_one(name_map) -> None:
    name_map.add("Total Gate Charge", "total_gate_charge_qg", None, approved=True)
    name_map.add("Total Gate Charge", "total_gate_charge_qg", "mosfet", approved=True)
    assert name_map.lookup("Total Gate Charge", "mosfet") == "total_gate_charge_qg"
    assert name_map.lookup("Total Gate Charge", None) == "total_gate_charge_qg"


def test_an_approved_mapping_wins_over_an_unapproved_one(name_map) -> None:
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=False)
    name_map.add("Qg", "gate_charge_total", "mosfet", approved=True)
    assert name_map.lookup("Qg", "mosfet") == "gate_charge_total"


def test_set_approved(name_map) -> None:
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=False)
    assert name_map.all_mappings("mosfet")[0]["approved"] == "no"
    changed = name_map.set_approved("Qg", True)
    assert changed == 1
    assert name_map.all_mappings("mosfet")[0]["approved"] == "yes"
    name_map.set_approved("Qg", "no")
    assert name_map.all_mappings("mosfet")[0]["approved"] == "no"


def test_remove(name_map) -> None:
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=True)
    assert name_map.remove("Qg", "mosfet") == 1
    assert name_map.lookup("Qg", "mosfet") is None


def test_the_mapping_is_a_dictionary(name_map) -> None:
    name_map.add("Qg", "total_gate_charge_qg", "mosfet", approved=True)
    mapping = name_map.all_mappings("mosfet")[0]
    assert mapping["raw_name"] == "Qg"
    assert mapping["standard_name"] == "total_gate_charge_qg"
    assert mapping["family"] == "mosfet"
    assert mapping["approved"] == "yes"
    assert mapping["id"] > 0
