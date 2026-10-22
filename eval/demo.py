"""A fixture backed demo of the evaluation harness.

The demo runs the six experiments of plan WP8 on the recorded fixtures in
``contracts/fixtures``. It uses a fake extractor, a fake validator, a fake
filter builder and a fake alternative finder, so it needs no network, no API
key and no LLM.

The fake extractor has a fixed quality. Each field has a *difficulty* score.
A tier reads the field when its coverage allows it, and it reads the field
correctly when the difficulty is below the accuracy of the tier. The
behaviour never changes between two runs.

Run it with::

    python -m eval demo
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.gold_set import GoldRow, load_gold_set
from eval.metrics import Value, field_accuracy, values_match
from eval.queries import QUERIES
from eval.runners import (
    experiment_1_tiers,
    experiment_2_tiered_vs_best,
    experiment_3_validation_on_off,
    experiment_4_search,
    experiment_5_alternatives,
    experiment_6_by_manufacturer,
    gold_to_mapping,
)

__all__ = [
    "FakeAlternativeFinder",
    "FakeExtractor",
    "FakeFilterBuilder",
    "FakeValidator",
    "REPO_ROOT",
    "run_demo",
]

#: The root of the repository.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: The gold set of the demo. It is the recorded fixture, not the real gold set.
DEMO_GOLD_SET = REPO_ROOT / "contracts" / "fixtures" / "gold" / "gold_set_example.csv"

#: The share of the fields that each tier reads at all.
_TIER_COVERAGE = {
    "tier1": 0.72,
    "tier2_text": 0.86,
    "tier2_tables": 0.93,
    "tier3": 0.98,
}

#: The accuracy of each tier. The difficulty of a field is the same for
#: every tier, so a field that tier 1 reads wrongly stays difficult.
_TIER_ACCURACY = {
    "tier1": 0.55,
    "tier2_text": 0.70,
    "tier2_tables": 0.82,
    "tier3": 0.93,
}

#: The cost of one datasheet per tier, in USD. The vision tier is the
#: expensive one, so the tiered use saves cost.
_TIER_COST = {
    "tier1": 0.0,
    "tier2_text": 0.0040,
    "tier2_tables": 0.0060,
    "tier3": 0.0500,
}

#: The time of one datasheet per tier, in ms.
_TIER_TIME = {
    "tier1": 240.0,
    "tier2_text": 1800.0,
    "tier2_tables": 2200.0,
    "tier3": 4500.0,
}

#: The order of the tiers.
_TIER_ORDER = ("tier1", "tier2_text", "tier2_tables", "tier3")


def _score(key: str) -> float:
    """Return a stable number between 0 and 1 for a key."""
    return (zlib.crc32(key.encode("utf-8")) % 10_000) / 10_000.0


class FakeExtractor:
    """A fake extractor with a fixed quality per tier.

    The fake reads the gold set and returns a value for each field. A field
    is wrong when the difficulty of the field is above the accuracy of the
    tier. The behaviour never changes between two runs.
    """

    def __init__(self, gold: Mapping[tuple[str, str], Value], tier: str) -> None:
        self._gold = dict(gold)
        self._tier = tier

    def _outcome(self, part_id: str) -> dict[str, Any]:
        accuracy = _TIER_ACCURACY.get(self._tier, 0.8)
        coverage = _TIER_COVERAGE.get(self._tier, 0.9)
        values: dict[str, Any] = {}
        failed: list[str] = []
        for (part, param), gold_value in self._gold.items():
            if part != part_id:
                continue
            if _score(f"cover:{self._tier}:{part}:{param}") >= coverage:
                failed.append(param)
                continue
            number = gold_value.value if gold_value.value is not None else 0.0
            if _score(f"difficulty:{part}:{param}") < accuracy:
                values[param] = {"value": number, "unit": gold_value.unit}
            else:
                values[param] = {"value": number * 1.4 + 0.5, "unit": gold_value.unit}
        return {
            "part_id": part_id,
            "tier": self._tier,
            "values": values,
            "failed_fields": failed,
            "cost": _TIER_COST.get(self._tier, 0.0),
            "duration_ms": _TIER_TIME.get(self._tier, 0.0),
        }

    def outcome(self, part_id: str) -> dict[str, Any]:
        """Return the outcome of this extractor for one part."""
        return self._outcome(part_id)

    def tier1(self, part_id: str) -> dict[str, Any]:
        return self._outcome(part_id)

    def tier2_text(self, part_id: str) -> dict[str, Any]:
        return self._outcome(part_id)

    def tier2_tables(self, part_id: str) -> dict[str, Any]:
        return self._outcome(part_id)

    def tier3(self, part_id: str) -> dict[str, Any]:
        return self._outcome(part_id)


class FakeValidator:
    """A fake validator with a range rule and an API cross-check.

    The API value stands in for the value that the distributor API returns.
    A value outside the range of the field is rejected. A value that differs
    from the API value goes to the review queue.
    """

    #: The range of each field. A value outside the range is rejected.
    RANGES: dict[str, tuple[float, float]] = {
        "vds_max": (1.0, 1200.0),
        "id_continuous": (0.01, 900.0),
        "rds_on": (0.01, 400.0),
        "vgs_threshold": (0.05, 15.0),
    }

    def status(self, param: str, value: float | None, api_value: float | None = None) -> str:
        """Return the status of one value."""
        if value is None:
            return "rejected"
        limits = self.RANGES.get(param)
        if limits is not None:
            low, high = limits
            if value < low or value > high:
                return "rejected"
        if api_value is not None and not values_match(value, api_value):
            return "review"
        return "accepted"


class FakeFilterBuilder:
    """A fake filter builder. It knows most of the test queries."""

    def __init__(self, failures: Sequence[str] = ()) -> None:
        self._failures = set(failures)

    def build(self, query: str) -> dict[str, Any]:
        for text, expected in QUERIES:
            if text == query and query not in self._failures:
                return json.loads(json.dumps(expected))
        return {}


class FakeAlternativeFinder:
    """A fake alternative finder. It returns three candidates per part."""

    def __init__(self, gold: Sequence[GoldRow]) -> None:
        self._parts = sorted({row.part_id for row in gold})

    def rank(self, part_id: str) -> list[str]:
        return [f"{part_id}-alt-{index}" for index in range(1, 4)]

    def experts(self) -> dict[str, list[str]]:
        """Return the alternatives that the experts accept."""
        out: dict[str, list[str]] = {}
        for part_id in self._parts:
            keep = 2 if _score(part_id) < 0.5 else 1
            out[part_id] = [f"{part_id}-alt-{index}" for index in range(1, keep + 1)]
        return out


def _validation_records(
    gold: Mapping[tuple[str, str], Value],
    validator: FakeValidator,
    use_validator: bool,
) -> list[dict[str, Any]]:
    """Build the records of the validation experiment.

    One value in five is wrong. The wrong value is out of the range of the
    field or it differs from the API value.
    """
    records: list[dict[str, Any]] = []
    for (part, param), gold_value in gold.items():
        number = gold_value.value if gold_value.value is not None else 0.0
        if _score(f"error:{part}:{param}") < 0.20:
            predicted = number * 8.0 + 12.0
        else:
            predicted = number
        status = validator.status(param, predicted, number) if use_validator else "accepted"
        records.append(
            {
                "part_id": part,
                "param": param,
                "gold": {"value": number, "unit": gold_value.unit},
                "predicted": {"value": predicted, "unit": gold_value.unit},
                "status": status,
            }
        )
    return records


def _tiered_run(
    gold: Mapping[tuple[str, str], Value],
    outcomes: Mapping[str, Mapping[str, dict[str, Any]]],
    parts: Sequence[str],
) -> tuple[dict[tuple[str, str], Value], float]:
    """Run the tiers in order and stop at the first tier that validates.

    The result holds the values that the run found and the cost of the run.
    """
    params_by_part: dict[str, list[str]] = {}
    for part, param in gold:
        params_by_part.setdefault(part, []).append(param)

    resolved: dict[str, set[str]] = {part: set() for part in parts}
    combined: dict[tuple[str, str], Value] = {}
    used: dict[str, set[str]] = {tier: set() for tier in _TIER_ORDER}

    for tier in _TIER_ORDER:
        for part in parts:
            pending = [
                param for param in params_by_part.get(part, []) if param not in resolved[part]
            ]
            if not pending:
                continue
            used[tier].add(part)
            values = outcomes[tier][part]["values"]
            for param in pending:
                raw = values.get(param)
                if raw is None:
                    continue
                if values_match(raw["value"], gold[(part, param)].value):
                    resolved[part].add(param)
                    combined[(part, param)] = Value(float(raw["value"]), raw.get("unit"))

    cost = sum(_TIER_COST[tier] * len(used[tier]) for tier in _TIER_ORDER)
    return combined, cost


def run_demo(
    gold_path: str | Path | None = None, output_dir: str | Path | None = None
) -> dict[str, Any]:
    """Run the six experiments on the fixtures and return the results.

    The result holds the numbers of every experiment, the markdown tables and
    the summary that the charts need.
    """
    path = Path(gold_path) if gold_path else DEMO_GOLD_SET
    rows = load_gold_set(path)
    gold = gold_to_mapping(rows)

    parts = sorted({part for part, _ in gold})
    manufacturers = {row.part_id: row.manufacturer for row in rows}

    extractor_tiers = {tier: FakeExtractor(gold, tier) for tier in _TIER_ORDER}

    experiment_1 = experiment_1_tiers(extractor_tiers, gold, parts=parts)

    outcomes = {
        tier: {part: extractor_tiers[tier].outcome(part) for part in parts} for tier in _TIER_ORDER
    }
    combined, tiered_cost = _tiered_run(gold, outcomes, parts)
    tiered = {"name": "tiered use", "accuracy": field_accuracy(combined, gold), "cost": tiered_cost}
    best = {
        "name": "always the best tier",
        "accuracy": experiment_1["tiers"]["tier3"]["accuracy"],
        "cost": experiment_1["tiers"]["tier3"]["cost"],
    }
    experiment_2 = experiment_2_tiered_vs_best(tiered, best)

    validator = FakeValidator()
    experiment_3 = experiment_3_validation_on_off(
        _validation_records(gold, validator, True),
        _validation_records(gold, validator, False),
    )

    builder = FakeFilterBuilder(failures={text for text, _ in QUERIES[::7]})
    nl_results = {text: builder.build(text) for text, _ in QUERIES}
    keyword_results = {text: (12 if index % 5 else 0) for index, (text, _) in enumerate(QUERIES)}
    experiment_4 = experiment_4_search(nl_results, keyword_results, QUERIES)

    finder = FakeAlternativeFinder(rows)
    ranked = {part_id: finder.rank(part_id) for part_id in parts}
    experiment_5 = experiment_5_alternatives(ranked, finder.experts())

    tier3_values = {part: outcomes["tier3"][part]["values"] for part in parts}
    rows_for_manufacturer: list[dict[str, Any]] = []
    for (part, param), gold_value in gold.items():
        raw = tier3_values[part].get(param)
        correct = raw is not None and values_match(raw["value"], gold_value.value)
        rows_for_manufacturer.append(
            {
                "part_id": part,
                "param": param,
                "manufacturer": manufacturers.get(part, "unknown"),
                "correct": correct,
            }
        )
    experiment_6 = experiment_6_by_manufacturer(rows_for_manufacturer)

    results: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "gold_set": str(path),
        "demo": True,
        "tiers": experiment_1["tiers"],
        "manufacturers": experiment_6["breakdown"],
        "confusion": experiment_3["validated"]["confusion"],
        "cost_vs_accuracy": [
            {"name": tier, "cost": data["cost"], "accuracy": data["accuracy"]}
            for tier, data in experiment_1["tiers"].items()
        ],
        "experiments": {
            "experiment_1_tiers": experiment_1,
            "experiment_2_tiered_vs_best": experiment_2,
            "experiment_3_validation_on_off": experiment_3,
            "experiment_4_search": experiment_4,
            "experiment_5_alternatives": experiment_5,
            "experiment_6_by_manufacturer": experiment_6,
        },
    }

    directory = Path(output_dir) if output_dir else Path(__file__).resolve().parent / "results"
    directory.mkdir(parents=True, exist_ok=True)
    results_path = directory / "demo_results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    results["results_file"] = str(results_path)
    return results
