"""Unit tests for the metric functions of ``eval.metrics``."""

from __future__ import annotations

import pytest

from eval.metrics import (
    EvalRow,
    UnitError,
    Value,
    accuracy_by_field,
    accuracy_by_manufacturer,
    build_rows,
    confusion,
    cost_per_datasheet,
    field_accuracy,
    latency_stats,
    mrr,
    normalise_value,
    precision_at_k,
    recall,
    refusal_rate,
    values_match,
)

# --------------------------------------------------------------------------------------
# normalise_value and values_match
# --------------------------------------------------------------------------------------


def test_normalise_value_converts_a_prefix_to_the_base_unit() -> None:
    value, unit = normalise_value(12.0, "mohm")
    assert unit == "ohm"
    assert value == pytest.approx(0.012)


def test_normalise_value_keeps_a_base_unit() -> None:
    value, unit = normalise_value(100.0, "V")
    assert (value, unit) == (100.0, "V")


def test_normalise_value_without_a_unit_is_dimensionless() -> None:
    assert normalise_value(3.0, None) == (3.0, None)
    assert normalise_value(3.0, "") == (3.0, None)


def test_normalise_value_with_none_returns_none() -> None:
    assert normalise_value(None, "V") == (None, "V")


def test_normalise_value_raises_on_an_unknown_unit() -> None:
    with pytest.raises(UnitError):
        normalise_value(1.0, "not-a-unit")


def test_values_match_accepts_a_relative_difference() -> None:
    assert values_match(Value(100.0, "V"), Value(104.0, "V")) is True
    assert values_match(Value(100.0, "V"), Value(110.0, "V")) is False


def test_values_match_converts_the_units_first() -> None:
    assert values_match(Value(12.0, "mohm"), Value(0.012, "ohm")) is True
    assert values_match(Value(1.0, "A"), Value(1000.0, "mA")) is True


def test_values_match_rejects_a_different_dimension() -> None:
    assert values_match(Value(12.0, "V"), Value(12.0, "A")) is False


def test_values_match_uses_the_absolute_tolerance_for_tiny_values() -> None:
    assert values_match(Value(0.0, "V"), Value(1e-12, "V")) is True


def test_values_match_rejects_none() -> None:
    assert values_match(None, Value(1.0, "V")) is False
    assert values_match(Value(1.0, "V"), None) is False


def test_values_match_accepts_plain_numbers() -> None:
    assert values_match(5.0, 5.0) is True
    assert values_match(5.0, 6.0) is False


# --------------------------------------------------------------------------------------
# field_accuracy
# --------------------------------------------------------------------------------------


def test_field_accuracy_counts_the_matching_pairs() -> None:
    gold = {
        ("p1", "vds_max"): Value(100.0, "V"),
        ("p1", "rds_on"): Value(10.0, "mohm"),
    }
    predictions = {
        ("p1", "vds_max"): Value(100.0, "V"),
        ("p1", "rds_on"): Value(50.0, "mohm"),
    }
    assert field_accuracy(predictions, gold) == pytest.approx(0.5)


def test_field_accuracy_counts_a_missing_prediction_as_wrong() -> None:
    gold = {("p1", "vds_max"): Value(100.0, "V")}
    assert field_accuracy({}, gold) == 0.0


def test_field_accuracy_of_an_empty_gold_set_is_zero() -> None:
    assert field_accuracy({}, {}) == 0.0


def test_field_accuracy_works_with_a_list_of_rows() -> None:
    gold = [{"part_id": "p1", "param_name": "vds_max", "value": 100.0, "unit": "V"}]
    predictions = [{"part_id": "p1", "param_name": "vds_max", "value": 100.0, "unit": "V"}]
    assert field_accuracy(predictions, gold) == pytest.approx(1.0)


def test_build_rows_pairs_the_prediction_with_the_gold_value() -> None:
    gold = {("p1", "vds_max"): Value(100.0, "V")}
    predictions = {("p1", "vds_max"): Value(100.0, "V"), ("p1", "other"): Value(1.0, "V")}
    rows = build_rows(predictions, gold)
    assert len(rows) == 1
    assert rows[0].is_correct() is True


def test_eval_row_without_a_prediction_is_wrong() -> None:
    row = EvalRow(part_id="p1", param="vds_max", gold=Value(100.0, "V"))
    assert row.is_correct() is False


# --------------------------------------------------------------------------------------
# precision, recall and mrr
# --------------------------------------------------------------------------------------


def test_precision_at_k_counts_the_hits_in_the_first_k() -> None:
    assert precision_at_k(["a", "b", "c", "d"], ["a", "d"], 3) == pytest.approx(1 / 3)


def test_precision_at_k_with_no_relevant_item_is_zero() -> None:
    assert precision_at_k(["a", "b"], [], 2) == 0.0


def test_precision_at_k_with_k_zero_is_zero() -> None:
    assert precision_at_k(["a"], ["a"], 0) == 0.0


def test_recall_finds_every_relevant_item() -> None:
    assert recall(["a", "b", "c"], ["a", "c", "d"]) == pytest.approx(2 / 3)


def test_recall_with_no_relevant_item_is_zero() -> None:
    assert recall(["a"], []) == 0.0


def test_mrr_uses_the_rank_of_the_first_relevant_item() -> None:
    assert mrr(["x", "y", "a"], ["a"]) == pytest.approx(1 / 3)


def test_mrr_without_a_relevant_item_is_zero() -> None:
    assert mrr(["x", "y"], ["a"]) == 0.0


def test_mrr_reads_the_part_of_an_alternative_object() -> None:
    class Part:
        part_id = "p2"

    class Alternative:
        part = Part()

    assert mrr([Alternative()], ["p2"]) == pytest.approx(1.0)


# --------------------------------------------------------------------------------------
# refusal_rate
# --------------------------------------------------------------------------------------


def test_refusal_rate_counts_the_refused_questions() -> None:
    results = [{"refused": True}, {"refused": False}, {"refused": True}]
    assert refusal_rate(results) == pytest.approx(2 / 3)


def test_refusal_rate_uses_the_given_refusal_list() -> None:
    results = [{"answer": "a"}, {"answer": "b"}, {"answer": "c"}]
    assert refusal_rate(results, [1]) == pytest.approx(1 / 3)


def test_refusal_rate_accepts_a_boolean_mask() -> None:
    results = ["a", "b", "c"]
    assert refusal_rate(results, [False, True, True]) == pytest.approx(2 / 3)


def test_refusal_rate_of_an_empty_list_is_zero() -> None:
    assert refusal_rate([]) == 0.0


# --------------------------------------------------------------------------------------
# cost_per_datasheet
# --------------------------------------------------------------------------------------


def test_cost_per_datasheet_divides_by_the_number_of_datasheets() -> None:
    calls = [
        {"cost": 0.01, "datasheet_id": "d1"},
        {"cost": 0.02, "datasheet_id": "d1"},
        {"cost": 0.03, "datasheet_id": "d2"},
    ]
    assert cost_per_datasheet(calls) == pytest.approx(0.03)


def test_cost_per_datasheet_accepts_a_mapping_of_datasheets() -> None:
    calls = {"d1": [{"cost": 0.01}], "d2": [{"cost": 0.03}]}
    assert cost_per_datasheet(calls) == pytest.approx(0.02)


def test_cost_per_datasheet_of_no_call_is_zero() -> None:
    assert cost_per_datasheet([]) == 0.0


# --------------------------------------------------------------------------------------
# latency_stats
# --------------------------------------------------------------------------------------


def test_latency_stats_gives_the_mean_the_median_and_the_p95() -> None:
    stats = latency_stats([10.0, 20.0, 30.0, 40.0, 100.0])
    assert stats["count"] == 5
    assert stats["mean"] == pytest.approx(40.0)
    assert stats["median"] == pytest.approx(30.0)
    assert stats["p95"] == pytest.approx(88.0)
    assert stats["max"] == 100.0


def test_latency_stats_of_an_empty_list_is_zero() -> None:
    stats = latency_stats([])
    assert stats["count"] == 0
    assert stats["mean"] == 0.0


# --------------------------------------------------------------------------------------
# confusion
# --------------------------------------------------------------------------------------


def test_confusion_counts_the_stopped_wrong_values() -> None:
    result = confusion(
        ["wrong", "wrong", "correct", "correct"],
        ["stopped", "accepted", "accepted", "stopped"],
    )
    assert result["wrong_stopped"] == 1
    assert result["wrong_missed"] == 1
    assert result["false_alarms"] == 1
    assert result["correct_accepted"] == 1
    assert result["stop_rate"] == pytest.approx(0.5)
    assert len(result["matrix"]) == len(result["labels"])
    assert sum(sum(line) for line in result["matrix"]) == 4


def test_confusion_needs_two_lists_of_the_same_length() -> None:
    with pytest.raises(ValueError):
        confusion(["wrong"], ["stopped", "accepted"])


# --------------------------------------------------------------------------------------
# grouped accuracy
# --------------------------------------------------------------------------------------


def test_accuracy_by_manufacturer_groups_the_rows() -> None:
    rows = [
        {"manufacturer": "TI", "param": "vds_max", "correct": True},
        {"manufacturer": "TI", "param": "rds_on", "correct": False},
        {"manufacturer": "onsemi", "param": "vds_max", "correct": True},
    ]
    result = accuracy_by_manufacturer(rows)
    assert result["TI"] == pytest.approx(0.5)
    assert result["onsemi"] == pytest.approx(1.0)


def test_accuracy_by_field_groups_the_rows() -> None:
    rows = [
        {"manufacturer": "TI", "param": "vds_max", "correct": True},
        {"manufacturer": "onsemi", "param": "vds_max", "correct": False},
    ]
    result = accuracy_by_field(rows)
    assert result["vds_max"] == pytest.approx(0.5)


def test_accuracy_by_manufacturer_accepts_a_summary_mapping() -> None:
    result = accuracy_by_manufacturer({"TI": {"correct": 9, "total": 10}})
    assert result["TI"] == pytest.approx(0.9)
