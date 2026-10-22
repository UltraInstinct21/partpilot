"""Tests for the demo and for the command line of the evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.__main__ import main
from eval.demo import DEMO_GOLD_SET, run_demo
from eval.gold_set import load_gold_set


def test_the_demo_gold_set_is_valid() -> None:
    assert load_gold_set(DEMO_GOLD_SET)


def test_the_demo_runs_every_experiment(tmp_path: Path) -> None:
    results = run_demo(output_dir=tmp_path)
    experiments = results["experiments"]
    assert set(experiments) == {
        "experiment_1_tiers",
        "experiment_2_tiered_vs_best",
        "experiment_3_validation_on_off",
        "experiment_4_search",
        "experiment_5_alternatives",
        "experiment_6_by_manufacturer",
    }
    assert 0.0 <= experiments["experiment_1_tiers"]["tiers"]["tier1"]["accuracy"] <= 1.0
    assert experiments["experiment_3_validation_on_off"]["additional_wrong_stopped"] >= 0


def test_the_demo_writes_the_results_file(tmp_path: Path) -> None:
    results = run_demo(output_dir=tmp_path)
    path = Path(results["results_file"])
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["demo"] is True
    assert payload["tiers"]


def test_the_tiered_use_costs_less_than_the_best_tier(tmp_path: Path) -> None:
    results = run_demo(output_dir=tmp_path)
    experiment = results["experiments"]["experiment_2_tiered_vs_best"]
    assert experiment["cost_saved"] > 0.0


def test_the_cli_validate_gold_accepts_a_valid_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["validate-gold", str(DEMO_GOLD_SET)])
    assert code == 0
    assert "valid" in capsys.readouterr().out


def test_the_cli_validate_gold_rejects_a_broken_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "gold.csv"
    path.write_text("part_id,mpn\np1,MPN\n", encoding="utf-8")
    code = main(["validate-gold", str(path)])
    assert code == 1
    assert "problem" in capsys.readouterr().out


def test_the_cli_queries_prints_the_thirty_queries(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["queries"])
    assert code == 0
    out = capsys.readouterr().out
    assert "30 queries, all valid." in out


def test_the_cli_demo_runs(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["demo", "--out", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Experiment 1" in out


def test_the_cli_help_works(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    assert "validate-gold" in capsys.readouterr().out
