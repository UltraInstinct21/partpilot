"""Tests for the chart functions of ``eval.charts``.

The charts need matplotlib. When it is not installed the tests are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.charts import (
    CHARTS,
    ChartsUnavailable,
    accuracy_by_manufacturer_chart,
    accuracy_by_tier_chart,
    confusion_matrix_chart,
    cost_by_tier_chart,
    cost_vs_accuracy_chart,
    load_results,
    render_all,
)

RESULTS = {
    "tiers": {
        "tier1": {"accuracy": 0.5, "cost": 0.0, "duration_ms": 1000},
        "tier2": {"accuracy": 0.8, "cost": 0.4, "duration_ms": 5000},
    },
    "manufacturers": {
        "TI": {"accuracy": 0.9, "correct": 9, "total": 10},
        "onsemi": {"accuracy": 0.7, "correct": 7, "total": 10},
    },
    "confusion": {
        "labels": ["accepted", "correct", "stopped", "wrong"],
        "matrix": [[0, 0, 0, 0], [0, 8, 0, 0], [0, 0, 0, 0], [0, 0, 2, 0]],
    },
    "cost_vs_accuracy": [
        {"name": "tier1", "cost": 0.0, "accuracy": 0.5},
        {"name": "tier2", "cost": 0.4, "accuracy": 0.8},
    ],
}


def test_load_results_reads_the_json_file(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(RESULTS), encoding="utf-8")
    assert load_results(path)["tiers"]["tier1"]["accuracy"] == 0.5


def test_load_results_rejects_a_json_array(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_results(path)


def test_the_chart_names_are_stable() -> None:
    assert CHARTS == (
        "accuracy_by_tier",
        "cost_by_tier",
        "accuracy_by_manufacturer",
        "validation_confusion",
        "cost_vs_accuracy",
    )


@pytest.mark.parametrize(
    "function,expected_name",
    [
        (accuracy_by_tier_chart, "accuracy_by_tier.png"),
        (cost_by_tier_chart, "cost_by_tier.png"),
        (accuracy_by_manufacturer_chart, "accuracy_by_manufacturer.png"),
        (confusion_matrix_chart, "validation_confusion.png"),
        (cost_vs_accuracy_chart, "cost_vs_accuracy.png"),
    ],
)
def test_every_chart_writes_a_png_file(
    function: object, expected_name: str, tmp_path: Path
) -> None:
    pytest.importorskip("matplotlib")
    path = function(RESULTS, tmp_path)  # type: ignore[operator]
    assert path.name == expected_name
    assert path.exists()
    assert path.stat().st_size > 0


def test_render_all_writes_every_chart(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    written = render_all(RESULTS, tmp_path)
    assert len(written) == len(CHARTS)


def test_a_chart_without_data_raises(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    with pytest.raises(ChartsUnavailable):
        accuracy_by_tier_chart({}, tmp_path)
