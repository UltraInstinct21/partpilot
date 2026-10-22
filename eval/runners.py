"""The six experiments of plan WP8.

Every experiment takes the implementation that it measures through
injection. Nothing is imported from another agent's package, so the harness
measures the real code, the fake code in the tests and the fixture backed
demo with the same functions.

The experiments are:

1. :func:`experiment_1_tiers` - Tier 1, Tier 2 text only, Tier 2 with tables
   and Tier 3.
2. :func:`experiment_2_tiered_vs_best` - the cost saved by the tiered use
   against the "always use the best tier" use.
3. :func:`experiment_3_validation_on_off` - the wrong values that the
   validator stops.
4. :func:`experiment_4_search` - the query success rate on the 30 queries.
5. :func:`experiment_5_alternatives` - the precision at 3 of the alternative
   finder.
6. :func:`experiment_6_by_manufacturer` - the accuracy per manufacturer.

Every experiment returns a dictionary with the metrics, the raw numbers and a
short markdown table under the key ``"markdown"``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from eval.metrics import (
    DEFAULT_ABS_TOLERANCE,
    DEFAULT_TOLERANCE,
    EvalRow,
    Value,
    accuracy_breakdown,
    build_rows,
    confusion,
    field_accuracy,
    mrr,
    precision_at_k,
    recall,
    values_match,
)

__all__ = [
    "TIER_ORDER",
    "TierExtractor",
    "experiment_1_tiers",
    "experiment_2_tiered_vs_best",
    "experiment_3_validation_on_off",
    "experiment_4_search",
    "experiment_5_alternatives",
    "experiment_6_by_manufacturer",
    "gold_to_mapping",
    "markdown_table",
]

#: The order of the tiers in experiment 1.
TIER_ORDER: tuple[str, ...] = ("tier1", "tier2_text", "tier2_tables", "tier3")

#: The method names that an injected extractor may use for each tier.
TIER_METHODS: dict[str, tuple[str, ...]] = {
    "tier1": ("tier1", "extract_tier1", "run_tier1"),
    "tier2_text": ("tier2_text", "extract_tier2_text", "tier2"),
    "tier2_tables": ("tier2_tables", "extract_tier2_tables"),
    "tier3": ("tier3", "extract_tier3"),
}

#: The keys of an outcome that are not parameter values.
_OUTCOME_META_KEYS = {
    "cost",
    "llm_cost",
    "duration_ms",
    "duration",
    "elapsed_ms",
    "failed_fields",
    "notes",
    "part_id",
    "tier",
    "scanned",
    "pages_used",
    "method",
    "source_id",
}

_STOPPED_STATUS = {"rejected", "review", "stopped", "blocked", "quarantined"}


@runtime_checkable
class TierExtractor(Protocol):
    """The interface that experiment 1 expects from an extractor.

    Any object with these methods works. The method may return a mapping of
    parameter name to value, a list of parameter objects, an object with a
    ``values`` list (the ``ExtractionResult`` of the contract) or a plain
    dictionary. The optional ``cost`` and ``duration_ms`` fields are read from
    the same object.
    """

    def tier1(self, part_id: str) -> Any: ...

    def tier2_text(self, part_id: str) -> Any: ...

    def tier2_tables(self, part_id: str) -> Any: ...

    def tier3(self, part_id: str) -> Any: ...


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Return a markdown table."""
    lines = ["| " + " | ".join(str(header) for header in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_value(value: Any) -> Value | None:
    """Convert a raw value into a :class:`~eval.metrics.Value`."""
    if value is None:
        return None
    if isinstance(value, Value):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Value(float(value), None)
    if isinstance(value, Mapping):
        raw = value.get("value")
        if raw is None:
            for key in ("value_typ", "value_max", "value_min"):
                if value.get(key) is not None:
                    raw = value[key]
                    break
        number = _as_float(raw)
        if number is None:
            return None
        unit = value.get("unit")
        return Value(number, None if unit is None else str(unit))
    raw = getattr(value, "value", None)
    if raw is None:
        for key in ("value_typ", "value_max", "value_min"):
            candidate = getattr(value, key, None)
            if candidate is not None:
                raw = candidate
                break
    number = _as_float(raw)
    if number is None:
        return None
    unit = getattr(value, "unit", None)
    return Value(number, None if unit is None else str(unit))


def gold_to_mapping(gold: Any) -> dict[tuple[str, str], Value]:
    """Convert any supported gold set into a ``{(part, param): Value}`` mapping."""
    out: dict[tuple[str, str], Value] = {}
    if gold is None:
        return out
    if isinstance(gold, Mapping):
        for key, raw in gold.items():
            if isinstance(key, tuple) and len(key) == 2:
                part, param = str(key[0]), str(key[1])
            elif isinstance(key, str) and ":" in key:
                part, param = key.split(":", 1)
            else:
                part, param = str(key), ""
            value = _coerce_value(raw)
            if value is not None:
                out[(part, param)] = value
        return out
    for item in gold:
        if isinstance(item, Mapping):
            part = str(item.get("part_id") or item.get("mpn") or "")
            param = str(item.get("param_name") or item.get("param") or item.get("name") or "")
            raw = item.get("value")
            if raw is None:
                raw = item.get("value_typ")
            unit = item.get("unit")
        else:
            part = str(getattr(item, "part_id", "") or getattr(item, "mpn", "") or "")
            param = str(
                getattr(item, "param_name", None)
                or getattr(item, "param", None)
                or getattr(item, "name", "")
                or ""
            )
            raw = getattr(item, "value", None)
            if raw is None:
                raw = getattr(item, "value_typ", None)
            unit = getattr(item, "unit", None)
        value = _coerce_value(raw if unit is None else {"value": raw, "unit": unit})
        if value is not None:
            out[(part, param)] = value
    return out


def _values_collection(items: Any) -> dict[str, Value]:
    """Turn a collection of parameters into a ``{name: Value}`` mapping."""
    out: dict[str, Value] = {}
    if items is None:
        return out
    if isinstance(items, Mapping):
        for name, raw in items.items():
            value = _coerce_value(raw)
            if value is not None:
                out[str(name)] = value
        return out
    if isinstance(items, (str, bytes)):
        return out
    for item in items:
        if isinstance(item, Mapping):
            name = item.get("name") or item.get("param") or item.get("param_name")
            raw = item.get("value")
            if raw is None:
                for key in ("value_typ", "value_max", "value_min"):
                    if item.get(key) is not None:
                        raw = item[key]
                        break
            unit = item.get("unit")
        else:
            name = getattr(item, "name", None) or getattr(item, "param", None)
            raw = getattr(item, "value", None)
            if raw is None:
                for key in ("value_typ", "value_max", "value_min"):
                    candidate = getattr(item, key, None)
                    if candidate is not None:
                        raw = candidate
                        break
            unit = getattr(item, "unit", None)
        if not name:
            continue
        value = _coerce_value(raw if unit is None else {"value": raw, "unit": unit})
        if value is not None:
            out[str(name)] = value
    return out


def _outcome_values(outcome: Any) -> dict[str, Value]:
    """Read the parameter values out of one extraction outcome."""
    if outcome is None:
        return {}
    if isinstance(outcome, Mapping):
        if "values" in outcome:
            return _values_collection(outcome["values"])
        return _values_collection(
            {key: value for key, value in outcome.items() if key not in _OUTCOME_META_KEYS}
        )
    values = getattr(outcome, "values", None)
    if values is not None:
        return _values_collection(values)
    return {}


def _outcome_number(outcome: Any, names: Sequence[str]) -> float:
    if outcome is None:
        return 0.0
    for name in names:
        if isinstance(outcome, Mapping):
            value = _as_float(outcome.get(name))
        else:
            value = _as_float(getattr(outcome, name, None))
        if value is not None:
            return value
    return 0.0


def _outcome_cost(outcome: Any) -> float:
    return _outcome_number(outcome, ("cost", "llm_cost", "total_cost"))


def _outcome_duration(outcome: Any) -> float:
    return _outcome_number(outcome, ("duration_ms", "duration", "elapsed_ms"))


# --------------------------------------------------------------------------------------
# Experiment 1: the tiers
# --------------------------------------------------------------------------------------


def _extractor_method(extractor: Any, tier: str) -> Any:
    for name in TIER_METHODS.get(tier, (tier,)):
        method = getattr(extractor, name, None)
        if callable(method):
            return method
    return None


def experiment_1_tiers(
    extractor: Any,
    gold: Any,
    *,
    parts: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
    cost_fn: Any = None,
    time_fn: Any = None,
    tolerance: float = DEFAULT_TOLERANCE,
    abs_tolerance: float = DEFAULT_ABS_TOLERANCE,
) -> dict[str, Any]:
    """Compare the four extraction tiers.

    ``extractor`` is either an object with the methods of
    :class:`TierExtractor` or a mapping ``{tier: {part_id: outcome}}``. The
    outcome of one part may be a mapping of parameter name to value, a list of
    parameter objects, an ``ExtractionResult`` or a plain dictionary with the
    optional keys ``cost`` and ``duration_ms``.

    ``gold`` is the gold set. It accepts the rows of ``load_gold_set``, a
    mapping ``{(part, param): value}`` or a list of dictionaries.

    ``cost_fn(tier, part_id)`` and ``time_fn(tier, part_id)`` may be used when
    the extractor does not report the cost or the duration itself.
    """
    gold_map = gold_to_mapping(gold)
    part_ids = list(parts) if parts else sorted({part for part, _ in gold_map})
    tier_names = list(tiers) if tiers else list(TIER_ORDER)

    per_tier: dict[str, dict[str, Any]] = {}
    for tier in tier_names:
        predictions: dict[tuple[str, str], Value] = {}
        total_cost = 0.0
        total_duration = 0.0
        extracted = 0
        missing = 0

        for part_id in part_ids:
            outcome: Any = None
            if isinstance(extractor, Mapping):
                bundle = extractor.get(tier)
                if isinstance(bundle, Mapping):
                    outcome = bundle.get(part_id)
                elif bundle is not None:
                    method = _extractor_method(bundle, tier)
                    if method is not None:
                        outcome = method(part_id)
            else:
                method = _extractor_method(extractor, tier)
                if method is not None:
                    outcome = method(part_id)
            values = _outcome_values(outcome)
            extracted += len(values)
            for name, value in values.items():
                predictions[(part_id, name)] = value
            if not values:
                missing += 1
            cost = _outcome_cost(outcome)
            if callable(cost_fn):
                cost = float(cost_fn(tier, part_id))
            total_cost += cost
            duration = _outcome_duration(outcome)
            if callable(time_fn):
                duration = float(time_fn(tier, part_id))
            total_duration += duration

        rows = build_rows(predictions, gold_map)
        correct = sum(1 for row in rows if row.is_correct(tolerance, abs_tolerance))
        total = len(rows)
        accuracy = (correct / total) if total else 0.0
        per_tier[tier] = {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "cost": total_cost,
            "cost_per_datasheet": (total_cost / len(part_ids)) if part_ids else 0.0,
            "duration_ms": total_duration,
            "duration_ms_mean": (total_duration / len(part_ids)) if part_ids else 0.0,
            "fields_extracted": extracted,
            "parts_without_values": missing,
            "parts": len(part_ids),
        }

    table = markdown_table(
        ["tier", "accuracy", "correct/total", "cost (USD)", "cost/datasheet", "mean time (ms)"],
        [
            [
                tier,
                f"{data['accuracy'] * 100:.1f} %",
                f"{data['correct']}/{data['total']}",
                f"{data['cost']:.4f}",
                f"{data['cost_per_datasheet']:.4f}",
                f"{data['duration_ms_mean']:.0f}",
            ]
            for tier, data in per_tier.items()
        ],
    )
    return {
        "name": "experiment_1_tiers",
        "tiers": per_tier,
        "gold_pairs": len(gold_map),
        "parts": len(part_ids),
        "markdown": table,
    }


# --------------------------------------------------------------------------------------
# Experiment 2: the tiered use against the best tier
# --------------------------------------------------------------------------------------


def _summary(value: Any, label: str) -> dict[str, float]:
    if isinstance(value, Mapping):
        accuracy = _as_float(value.get("accuracy"))
        cost = _as_float(value.get("cost"))
        if cost is None:
            cost = _as_float(value.get("total_cost"))
        name = str(value.get("name", label))
    else:
        accuracy = _as_float(getattr(value, "accuracy", None))
        cost = _as_float(getattr(value, "cost", None))
        name = str(getattr(value, "name", label))
    if accuracy is None:
        raise ValueError(f"{label} must hold an 'accuracy' number")
    if cost is None:
        raise ValueError(f"{label} must hold a 'cost' number")
    return {"name": name, "accuracy": accuracy, "cost": cost}


def experiment_2_tiered_vs_best(
    tiered_results: Any,
    best_tier_results: Any,
    *,
    accuracy_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Return the cost that the tiered use saves against the best tier.

    Both arguments hold an ``accuracy`` and a ``cost``. They may be
    dictionaries or objects with the same attribute names.
    """
    tiered = _summary(tiered_results, "tiered_results")
    best = _summary(best_tier_results, "best_tier_results")

    cost_saved = best["cost"] - tiered["cost"]
    cost_saved_pct = (cost_saved / best["cost"]) if best["cost"] else 0.0
    accuracy_delta = tiered["accuracy"] - best["accuracy"]
    equivalent = abs(accuracy_delta) <= accuracy_tolerance

    table = markdown_table(
        ["run", "accuracy", "cost (USD)"],
        [
            [tiered["name"], f"{tiered['accuracy'] * 100:.1f} %", f"{tiered['cost']:.4f}"],
            [best["name"], f"{best['accuracy'] * 100:.1f} %", f"{best['cost']:.4f}"],
            [
                "cost saved",
                f"{accuracy_delta * 100:+.1f} points",
                f"{cost_saved:.4f} ({cost_saved_pct * 100:.1f} %)",
            ],
        ],
    )
    return {
        "name": "experiment_2_tiered_vs_best",
        "tiered": tiered,
        "best": best,
        "cost_saved": cost_saved,
        "cost_saved_pct": cost_saved_pct,
        "accuracy_delta": accuracy_delta,
        "accuracy_equivalent": equivalent,
        "markdown": table,
    }


# --------------------------------------------------------------------------------------
# Experiment 3: the validation on and off
# --------------------------------------------------------------------------------------


@dataclass
class _ValidationRecord:
    gold: Any = None
    predicted: Any = None
    status: str = ""


def _validation_record(item: Any) -> _ValidationRecord:
    if isinstance(item, EvalRow):
        return _ValidationRecord(gold=item.gold, predicted=item.predicted, status=item.status or "")
    if isinstance(item, Mapping):
        gold = item.get("gold", item.get("gold_value"))
        predicted = item.get("predicted", item.get("predicted_value"))
        if gold is None and predicted is None and "value" in item:
            gold = item.get("value")
            predicted = item.get("value")
        status = str(item.get("status", "") or "")
        if not status and item.get("rejected"):
            status = "rejected"
        if not status and item.get("stopped"):
            status = "stopped"
        return _ValidationRecord(gold=gold, predicted=predicted, status=status)
    return _ValidationRecord(
        gold=getattr(item, "gold", None),
        predicted=getattr(item, "predicted", None),
        status=str(getattr(item, "status", "") or ""),
    )


def _validation_stats(
    records: Sequence[Any], tolerance: float, abs_tolerance: float
) -> dict[str, Any]:
    truths: list[str] = []
    predictions: list[str] = []
    for item in records:
        record = _validation_record(item)
        is_wrong = not values_match(
            record.predicted, record.gold, tolerance=tolerance, abs_tolerance=abs_tolerance
        )
        truths.append("wrong" if is_wrong else "correct")
        stopped = record.status.strip().lower() in _STOPPED_STATUS
        predictions.append("stopped" if stopped else "accepted")
    matrix = confusion(truths, predictions)
    return {
        "total": len(records),
        "wrong": matrix["wrong_stopped"] + matrix["wrong_missed"],
        "stopped": matrix["wrong_stopped"] + matrix["false_alarms"],
        "wrong_stopped": matrix["wrong_stopped"],
        "wrong_missed": matrix["wrong_missed"],
        "false_alarms": matrix["false_alarms"],
        "correct_accepted": matrix["correct_accepted"],
        "stop_rate": matrix["stop_rate"],
        "stop_precision": matrix["stop_precision"],
        "confusion": matrix,
    }


def experiment_3_validation_on_off(
    validated: Sequence[Any],
    unvalidated: Sequence[Any],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    abs_tolerance: float = DEFAULT_ABS_TOLERANCE,
) -> dict[str, Any]:
    """Count the wrong values that the validator stops.

    Both arguments hold one record per value. A record holds the gold value,
    the predicted value and the status of the value. The status ``rejected``
    or ``review`` means that the validator stopped the value.
    """
    on = _validation_stats(list(validated), tolerance, abs_tolerance)
    off = _validation_stats(list(unvalidated), tolerance, abs_tolerance)
    extra = on["wrong_stopped"] - off["wrong_stopped"]

    table = markdown_table(
        ["mode", "values", "wrong", "wrong stopped", "wrong missed", "stop rate"],
        [
            [
                "validation on",
                on["total"],
                on["wrong"],
                on["wrong_stopped"],
                on["wrong_missed"],
                f"{on['stop_rate'] * 100:.1f} %",
            ],
            [
                "validation off",
                off["total"],
                off["wrong"],
                off["wrong_stopped"],
                off["wrong_missed"],
                f"{off['stop_rate'] * 100:.1f} %",
            ],
            [
                "difference",
                on["total"] - off["total"],
                on["wrong"] - off["wrong"],
                extra,
                on["wrong_missed"] - off["wrong_missed"],
                f"{(on['stop_rate'] - off['stop_rate']) * 100:+.1f} points",
            ],
        ],
    )
    return {
        "name": "experiment_3_validation_on_off",
        "validated": on,
        "unvalidated": off,
        "additional_wrong_stopped": extra,
        "markdown": table,
    }


# --------------------------------------------------------------------------------------
# Experiment 4: the natural-language search
# --------------------------------------------------------------------------------------


def _filter_to_dict(produced: Any) -> dict[str, Any]:
    if produced is None:
        return {}
    if isinstance(produced, Mapping):
        if "filter" in produced and isinstance(produced["filter"], Mapping):
            return dict(produced["filter"])
        return {key: value for key, value in produced.items() if value is not None}
    dump = getattr(produced, "model_dump", None)
    if callable(dump):
        return {key: value for key, value in dump(exclude_none=True).items() if value is not None}
    return {}


def _constraint_name(constraint: Any) -> str:
    if isinstance(constraint, Mapping):
        return str(constraint.get("name", ""))
    return str(getattr(constraint, "name", ""))


def _constraint_value(constraint: Any, key: str) -> Any:
    if isinstance(constraint, Mapping):
        return constraint.get(key)
    return getattr(constraint, key, None)


def _same_number(a: Any, b: Any, tolerance: float) -> bool:
    left = _as_float(a)
    right = _as_float(b)
    if left is None or right is None:
        return a == b
    scale = max(abs(left), abs(right))
    return abs(left - right) <= max(1e-12, tolerance * scale)


def _same_value(produced: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(expected, bool) or isinstance(produced, bool):
        return produced == expected
    if isinstance(expected, (int, float)):
        return _same_number(produced, expected, tolerance)
    if isinstance(expected, (list, tuple, set)):
        produced_list = produced if isinstance(produced, (list, tuple, set)) else [produced]
        return set(map(str, expected)) == set(map(str, produced_list))
    if isinstance(expected, str):
        return str(produced).strip().lower() == expected.strip().lower()
    return produced == expected


def _filter_score(
    produced: Any, expected: Any, tolerance: float = DEFAULT_TOLERANCE
) -> tuple[float, list[str]]:
    """Return the share of the expected filter that the produced filter holds."""
    produced_dict = _filter_to_dict(produced)
    if not expected:
        return 1.0, []
    expected_dict = (
        _filter_to_dict(expected) if not isinstance(expected, Mapping) else dict(expected)
    )
    if not expected_dict:
        return 1.0, []

    checks = 0
    passed = 0
    problems: list[str] = []

    for key, expected_value in expected_dict.items():
        if expected_value is None:
            continue
        checks += 1
        if key == "parameters":
            ok = True
            expected_constraints = (
                expected_value if isinstance(expected_value, (list, tuple)) else [expected_value]
            )
            produced_constraints = produced_dict.get("parameters") or []
            for constraint in expected_constraints:
                name = _constraint_name(constraint)
                match = next(
                    (item for item in produced_constraints if _constraint_name(item) == name),
                    None,
                )
                if match is None:
                    ok = False
                    problems.append(f"the constraint {name!r} is missing")
                    continue
                for bound in ("min", "max", "typ", "operator"):
                    wanted = _constraint_value(constraint, bound)
                    if wanted is None:
                        continue
                    got = _constraint_value(match, bound)
                    if not _same_value(got, wanted, tolerance):
                        ok = False
                        problems.append(
                            f"the constraint {name!r} has {bound}={got!r}, expected {wanted!r}"
                        )
            if ok:
                passed += 1
            continue

        if key not in produced_dict:
            problems.append(f"the key {key!r} is missing")
            continue
        if _same_value(produced_dict[key], expected_value, tolerance):
            passed += 1
        else:
            problems.append(
                f"the key {key!r} is {produced_dict[key]!r}, expected {expected_value!r}"
            )

    if checks == 0:
        return 1.0, []
    return passed / checks, problems


def _query_list(queries: Any) -> list[tuple[str, str, Any]]:
    out: list[tuple[str, str, Any]] = []
    if queries is None:
        return []
    if isinstance(queries, Mapping):
        for query, expected in queries.items():
            out.append((str(query), str(query), expected))
        return out
    for item in queries:
        if isinstance(item, tuple) and len(item) == 2:
            out.append((str(item[0]), str(item[0]), item[1]))
        elif isinstance(item, Mapping):
            query = str(item.get("query", ""))
            out.append((query, query, item.get("expected", item.get("filter"))))
        else:
            out.append((str(item), str(item), None))
    return out


def _lookup(results: Any, query: str, index: int) -> Any:
    if results is None:
        return None
    if isinstance(results, Mapping):
        return results.get(query)
    items = list(results)
    if index < len(items):
        return items[index]
    return None


def _keyword_success(value: Any, expected: Any, tolerance: float) -> tuple[bool, float]:
    """Return the success of a keyword search."""
    if value is None:
        return False, 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value > 0), 1.0 if value > 0 else 0.0
    if isinstance(value, Mapping) and "total" in value:
        total = _as_float(value.get("total")) or 0.0
        return bool(total > 0), 1.0 if total > 0 else 0.0
    score, _ = _filter_score(value, expected, tolerance)
    return score >= 1.0, score


def experiment_4_search(
    nl_results: Any,
    keyword_results: Any,
    queries: Any,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Measure the query success of the natural-language and the keyword search.

    ``queries`` is the list of ``(query, expected_filter)`` pairs. The
    expected filter is a small dictionary, for example
    ``{"family": "mosfet", "parameters": [{"name": "rds_on", "max": 5.0}]}``.

    ``nl_results`` holds the filter that the search service built for each
    query. It may be a mapping ``{query: filter}`` or a list that follows the
    order of the queries. ``keyword_results`` holds the result of the keyword
    search. A number means the number of results, a mapping with a ``total``
    key means the same, and any other mapping is read as a filter and is
    compared with the expected filter.
    """
    query_list = _query_list(queries)
    per_query: list[dict[str, Any]] = []
    nl_hits = 0
    keyword_hits = 0
    combined_hits = 0
    nl_score_total = 0.0

    for index, (query, key, expected) in enumerate(query_list):
        nl_value = _lookup(nl_results, key, index)
        nl_score, nl_problems = _filter_score(nl_value, expected, tolerance)
        nl_ok = nl_score >= 1.0
        keyword_value = _lookup(keyword_results, key, index)
        keyword_ok, keyword_score = _keyword_success(keyword_value, expected, tolerance)
        if nl_ok:
            nl_hits += 1
        if keyword_ok:
            keyword_hits += 1
        if nl_ok and keyword_ok:
            combined_hits += 1
        nl_score_total += nl_score
        per_query.append(
            {
                "query": query,
                "nl_success": nl_ok,
                "nl_score": nl_score,
                "nl_problems": nl_problems,
                "keyword_success": keyword_ok,
                "keyword_score": keyword_score,
            }
        )

    total = len(query_list)
    nl_rate = (nl_hits / total) if total else 0.0
    keyword_rate = (keyword_hits / total) if total else 0.0
    combined_rate = (combined_hits / total) if total else 0.0

    table = markdown_table(
        ["search", "success", "rate"],
        [
            ["natural language", f"{nl_hits}/{total}", f"{nl_rate * 100:.1f} %"],
            ["keyword", f"{keyword_hits}/{total}", f"{keyword_rate * 100:.1f} %"],
            ["both", f"{combined_hits}/{total}", f"{combined_rate * 100:.1f} %"],
        ],
    )
    return {
        "name": "experiment_4_search",
        "queries": total,
        "nl_success_rate": nl_rate,
        "keyword_success_rate": keyword_rate,
        "combined_success_rate": combined_rate,
        "nl_mean_score": (nl_score_total / total) if total else 0.0,
        "per_query": per_query,
        "markdown": table,
    }


# --------------------------------------------------------------------------------------
# Experiment 5: the alternative finder
# --------------------------------------------------------------------------------------


def _identifier(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        for key in ("part_id", "mpn", "id", "alternative_id"):
            if item.get(key):
                return str(item[key])
        part = item.get("part")
        if part is not None:
            return _identifier(part)
        return ""
    for key in ("part_id", "mpn", "id", "alternative_id"):
        value = getattr(item, key, None)
        if value:
            return str(value)
    part = getattr(item, "part", None)
    if part is not None:
        return _identifier(part)
    return str(item)


def _ranked_lists(ranked: Any) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    if ranked is None:
        return out
    if isinstance(ranked, Mapping):
        for key, value in ranked.items():
            out[str(key)] = (
                list(value)
                if isinstance(value, Iterable) and not isinstance(value, str)
                else [value]
            )
        return out
    for item in ranked:
        part = getattr(item, "part", None)
        part_id = getattr(part, "part_id", None) if part is not None else None
        if part_id is None and isinstance(item, Mapping):
            part_id = item.get("part_id")
        if part_id is None:
            part_id = getattr(item, "part_id", None)
        alternatives = getattr(item, "alternatives", None)
        if alternatives is None and isinstance(item, Mapping):
            alternatives = item.get("alternatives")
        if part_id is not None and alternatives is not None:
            out[str(part_id)] = list(alternatives)
    return out


def _expert_sets(expert_labels: Any) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    if expert_labels is None:
        return out
    if isinstance(expert_labels, Mapping):
        for key, value in expert_labels.items():
            if isinstance(value, (str, bytes)):
                out[str(key)] = [value]
            elif isinstance(value, Iterable):
                out[str(key)] = list(value)
            else:
                out[str(key)] = [value]
        return out
    for item in expert_labels:
        if isinstance(item, Mapping):
            part = str(item.get("part_id", ""))
            relevant = item.get("relevant", item.get("accepted", []))
            if isinstance(relevant, (str, bytes)):
                relevant = [relevant]
            out[part] = list(relevant)
    return out


def experiment_5_alternatives(ranked: Any, expert_labels: Any) -> dict[str, Any]:
    """Measure the precision at 3 of the alternative finder.

    ``ranked`` holds the ranked alternatives per part. It may be a mapping
    ``{part_id: [alternative, ...]}`` or a list of objects with an
    ``alternatives`` list. ``expert_labels`` holds the alternatives that the
    experts accept, per part.
    """
    lists = _ranked_lists(ranked)
    experts = _expert_sets(expert_labels)

    per_part: dict[str, dict[str, float]] = {}
    precision_scores: list[float] = []
    precision_one_scores: list[float] = []
    recall_scores: list[float] = []
    reciprocal_scores: list[float] = []

    for part_id, items in lists.items():
        relevant = experts.get(part_id, [])
        p3 = precision_at_k(items, relevant, 3)
        p1 = precision_at_k(items, relevant, 1)
        rec = recall(items, relevant)
        rr = mrr(items, relevant)
        per_part[part_id] = {
            "precision_at_3": p3,
            "precision_at_1": p1,
            "recall": rec,
            "mrr": rr,
            "relevant": len(list(relevant)),
            "ranked": len(items),
        }
        precision_scores.append(p3)
        precision_one_scores.append(p1)
        recall_scores.append(rec)
        reciprocal_scores.append(rr)

    def mean(values: Sequence[float]) -> float:
        return (sum(values) / len(values)) if values else 0.0

    table = markdown_table(
        ["part", "precision@3", "precision@1", "recall", "mrr"],
        [
            [
                part_id,
                f"{data['precision_at_3'] * 100:.1f} %",
                f"{data['precision_at_1'] * 100:.1f} %",
                f"{data['recall'] * 100:.1f} %",
                f"{data['mrr']:.3f}",
            ]
            for part_id, data in per_part.items()
        ],
    )
    return {
        "name": "experiment_5_alternatives",
        "precision_at_3": mean(precision_scores),
        "precision_at_1": mean(precision_one_scores),
        "recall": mean(recall_scores),
        "mrr": mean(reciprocal_scores),
        "parts": len(per_part),
        "per_part": per_part,
        "markdown": table,
    }


# --------------------------------------------------------------------------------------
# Experiment 6: the accuracy per manufacturer
# --------------------------------------------------------------------------------------


def experiment_6_by_manufacturer(results: Any) -> dict[str, Any]:
    """Return the field accuracy per manufacturer.

    ``results`` holds the scored rows. A row may be an
    :class:`~eval.metrics.EvalRow`, a mapping with the keys ``manufacturer``,
    ``param`` and ``correct``, or a tuple ``(manufacturer, param, correct)``.
    """
    breakdown = accuracy_breakdown(results, "manufacturer")
    table = markdown_table(
        ["manufacturer", "accuracy", "correct/total"],
        [
            [
                name,
                f"{data['accuracy'] * 100:.1f} %",
                f"{int(data['correct'])}/{int(data['total'])}",
            ]
            for name, data in sorted(breakdown.items())
        ],
    )
    return {
        "name": "experiment_6_by_manufacturer",
        "accuracy_by_manufacturer": {name: data["accuracy"] for name, data in breakdown.items()},
        "breakdown": breakdown,
        "markdown": table,
    }


def field_accuracy_of(predictions: Any, gold: Any, **kwargs: Any) -> float:
    """Return the field accuracy of a prediction mapping against a gold set."""
    return field_accuracy(predictions, gold_to_mapping(gold), **kwargs)
