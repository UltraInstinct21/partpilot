"""Tests for the six experiments of ``eval.runners``."""

from __future__ import annotations

from typing import Any

import pytest
from eval.metrics import Value
from eval.runners import (
    experiment_1_tiers,
    experiment_2_tiered_vs_best,
    experiment_3_validation_on_off,
    experiment_4_search,
    experiment_5_alternatives,
    experiment_6_by_manufacturer,
    gold_to_mapping,
    markdown_table,
)

GOLD = {
    ("p1", "vds_max"): Value(100.0, "V"),
    ("p1", "rds_on"): Value(10.0, "mohm"),
    ("p2", "vds_max"): Value(60.0, "V"),
    ("p2", "rds_on"): Value(5.0, "mohm"),
}


class FakeExtractor:
    """A tiny fake extractor. It returns the values it was built with."""

    def __init__(self, values: dict[str, dict[str, Any]]) -> None:
        self._values = values

    def tier1(self, part_id: str) -> Any:
        return self._values.get("tier1", {}).get(part_id)

    def tier2_text(self, part_id: str) -> Any:
        return self._values.get("tier2_text", {}).get(part_id)

    def tier2_tables(self, part_id: str) -> Any:
        return self._values.get("tier2_tables", {}).get(part_id)

    def tier3(self, part_id: str) -> Any:
        return self._values.get("tier3", {}).get(part_id)


def _outcome(
    values: dict[str, Any], cost: float = 0.0, duration_ms: float = 100.0
) -> dict[str, Any]:
    return {"values": values, "cost": cost, "duration_ms": duration_ms}


# --------------------------------------------------------------------------------------
# Experiment 1
# --------------------------------------------------------------------------------------


def test_experiment_1_measures_the_accuracy_of_every_tier() -> None:
    extractor = FakeExtractor(
        {
            "tier1": {
                "p1": _outcome({"vds_max": {"value": 100.0, "unit": "V"}}),
                "p2": _outcome({"vds_max": {"value": 90.0, "unit": "V"}}),
            },
            "tier2_text": {
                "p1": _outcome({"vds_max": {"value": 100.0, "unit": "V"}}),
                "p2": _outcome({"vds_max": {"value": 60.0, "unit": "V"}}),
            },
        }
    )
    result = experiment_1_tiers(extractor, GOLD, tiers=("tier1", "tier2_text"))
    assert result["tiers"]["tier1"]["accuracy"] == pytest.approx(0.25)
    assert result["tiers"]["tier2_text"]["accuracy"] == pytest.approx(0.5)
    assert result["gold_pairs"] == 4
    assert "tier1" in result["markdown"]


def test_experiment_1_reads_the_cost_and_the_time() -> None:
    extractor = FakeExtractor(
        {"tier1": {"p1": _outcome({"vds_max": {"value": 100.0, "unit": "V"}}, 0.02, 250.0)}}
    )
    result = experiment_1_tiers(extractor, GOLD, tiers=("tier1",))
    assert result["tiers"]["tier1"]["cost"] == pytest.approx(0.02)
    assert result["tiers"]["tier1"]["duration_ms"] == pytest.approx(250.0)


def test_experiment_1_accepts_a_mapping_of_outcomes() -> None:
    bundle = {
        "tier1": {
            "p1": _outcome({"vds_max": {"value": 100.0, "unit": "V"}}),
            "p2": _outcome({"vds_max": {"value": 60.0, "unit": "V"}}),
        }
    }
    result = experiment_1_tiers(bundle, GOLD, tiers=("tier1",))
    assert result["tiers"]["tier1"]["accuracy"] == pytest.approx(0.5)


def test_experiment_1_accepts_a_mapping_of_extractors() -> None:
    bundle = {
        "tier1": FakeExtractor(
            {
                "tier1": {
                    "p1": _outcome({"vds_max": {"value": 100.0, "unit": "V"}}),
                    "p2": _outcome({"vds_max": {"value": 60.0, "unit": "V"}}),
                }
            }
        )
    }
    result = experiment_1_tiers(bundle, GOLD, tiers=("tier1",))
    assert result["tiers"]["tier1"]["accuracy"] == pytest.approx(0.5)


def test_experiment_1_counts_a_missing_field_as_wrong() -> None:
    extractor = FakeExtractor({"tier1": {"p1": _outcome({})}})
    result = experiment_1_tiers(extractor, GOLD, tiers=("tier1",))
    assert result["tiers"]["tier1"]["accuracy"] == 0.0
    assert result["tiers"]["tier1"]["parts_without_values"] == 2


def test_experiment_1_uses_the_cost_function() -> None:
    extractor = FakeExtractor({"tier1": {"p1": _outcome({})}})
    result = experiment_1_tiers(
        extractor,
        GOLD,
        tiers=("tier1",),
        cost_fn=lambda tier, part: 0.5,
        time_fn=lambda tier, part: 10.0,
    )
    assert result["tiers"]["tier1"]["cost"] == pytest.approx(1.0)
    assert result["tiers"]["tier1"]["duration_ms"] == pytest.approx(20.0)


# --------------------------------------------------------------------------------------
# Experiment 2
# --------------------------------------------------------------------------------------


def test_experiment_2_reports_the_saved_cost() -> None:
    result = experiment_2_tiered_vs_best(
        {"name": "tiered", "accuracy": 0.90, "cost": 0.10},
        {"name": "best", "accuracy": 0.90, "cost": 0.40},
    )
    assert result["cost_saved"] == pytest.approx(0.30)
    assert result["cost_saved_pct"] == pytest.approx(0.75)
    assert result["accuracy_equivalent"] is True


def test_experiment_2_reports_an_accuracy_difference() -> None:
    result = experiment_2_tiered_vs_best(
        {"accuracy": 0.80, "cost": 0.10},
        {"accuracy": 0.95, "cost": 0.40},
    )
    assert result["accuracy_delta"] == pytest.approx(-0.15)
    assert result["accuracy_equivalent"] is False


def test_experiment_2_needs_an_accuracy_and_a_cost() -> None:
    with pytest.raises(ValueError):
        experiment_2_tiered_vs_best({"cost": 1.0}, {"accuracy": 1.0, "cost": 1.0})


# --------------------------------------------------------------------------------------
# Experiment 3
# --------------------------------------------------------------------------------------


def test_experiment_3_counts_the_wrong_values_that_are_stopped() -> None:
    records = [
        {
            "gold": {"value": 100.0, "unit": "V"},
            "predicted": {"value": 120.0, "unit": "V"},
            "status": "rejected",
        },
        {
            "gold": {"value": 60.0, "unit": "V"},
            "predicted": {"value": 60.0, "unit": "V"},
            "status": "accepted",
        },
    ]
    result = experiment_3_validation_on_off(
        records, [dict(item, status="accepted") for item in records]
    )
    assert result["validated"]["wrong"] == 1
    assert result["validated"]["wrong_stopped"] == 1
    assert result["unvalidated"]["wrong_stopped"] == 0
    assert result["additional_wrong_stopped"] == 1


def test_experiment_3_counts_a_review_status_as_stopped() -> None:
    records = [
        {"gold": 1.0, "predicted": 2.0, "status": "review"},
    ]
    result = experiment_3_validation_on_off(records, records)
    assert result["validated"]["wrong_stopped"] == 1
    assert result["validated"]["false_alarms"] == 0


# --------------------------------------------------------------------------------------
# Experiment 4
# --------------------------------------------------------------------------------------


def test_experiment_4_counts_the_query_success() -> None:
    queries = [
        ("q1", {"family": "mosfet"}),
        ("q2", {"family": "gate_driver"}),
    ]
    nl = {"q1": {"family": "mosfet"}, "q2": {"family": "mosfet"}}
    keyword = {"q1": 5, "q2": 0}
    result = experiment_4_search(nl, keyword, queries)
    assert result["nl_success_rate"] == pytest.approx(0.5)
    assert result["keyword_success_rate"] == pytest.approx(0.5)
    assert result["combined_success_rate"] == pytest.approx(0.5)
    assert len(result["per_query"]) == 2


def test_experiment_4_checks_the_parameter_constraints() -> None:
    queries = [("q1", {"parameters": [{"name": "rds_on", "max": 5.0}]})]
    good = {"q1": {"parameters": [{"name": "rds_on", "max": 5.0, "unit": "mohm"}]}}
    bad = {"q1": {"parameters": [{"name": "rds_on", "max": 50.0}]}}
    assert experiment_4_search(good, good, queries)["nl_success_rate"] == pytest.approx(1.0)
    assert experiment_4_search(bad, bad, queries)["nl_success_rate"] == pytest.approx(0.0)


def test_experiment_4_gives_a_partial_score() -> None:
    queries = [("q1", {"family": "mosfet", "in_stock": True})]
    partial = {"q1": {"family": "mosfet"}}
    result = experiment_4_search(partial, partial, queries)
    assert result["nl_mean_score"] == pytest.approx(0.5)


# --------------------------------------------------------------------------------------
# Experiment 5
# --------------------------------------------------------------------------------------


def test_experiment_5_measures_the_precision_at_three() -> None:
    ranked = {"p1": ["a1", "a2", "a3", "a4"], "p2": ["b1", "b2", "b3"]}
    experts = {"p1": ["a1"], "p2": ["b2"]}
    result = experiment_5_alternatives(ranked, experts)
    assert result["precision_at_3"] == pytest.approx((1 / 3 + 1 / 3) / 2)
    assert result["precision_at_1"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(1.0)
    assert result["parts"] == 2


def test_experiment_5_accepts_objects_with_a_part() -> None:
    class Part:
        part_id = "p9"

    class Alternative:
        part = Part()

    result = experiment_5_alternatives({"p9": [Alternative()]}, {"p9": ["p9"]})
    assert result["precision_at_3"] == pytest.approx(1 / 3)


# --------------------------------------------------------------------------------------
# Experiment 6
# --------------------------------------------------------------------------------------


def test_experiment_6_groups_the_accuracy_by_manufacturer() -> None:
    rows = [
        {"manufacturer": "TI", "param": "vds_max", "correct": True},
        {"manufacturer": "TI", "param": "rds_on", "correct": False},
        {"manufacturer": "onsemi", "param": "vds_max", "correct": True},
    ]
    result = experiment_6_by_manufacturer(rows)
    assert result["accuracy_by_manufacturer"]["TI"] == pytest.approx(0.5)
    assert result["accuracy_by_manufacturer"]["onsemi"] == pytest.approx(1.0)
    assert "TI" in result["markdown"]


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def test_gold_to_mapping_reads_the_gold_rows() -> None:
    rows = [
        {"part_id": "p1", "param_name": "vds_max", "value": 100.0, "unit": "V"},
    ]
    mapping = gold_to_mapping(rows)
    assert mapping[("p1", "vds_max")] == Value(100.0, "V")


def test_markdown_table_has_a_header_and_a_line_for_every_row() -> None:
    table = markdown_table(["a", "b"], [[1, 2], [3, 4]])
    lines = table.splitlines()
    assert len(lines) == 4
    assert lines[0] == "| a | b |"
    assert lines[1] == "| --- | --- |"
