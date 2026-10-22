"""Pure metric functions for the PartPilot evaluation (plan WP8).

Every function in this module is pure. It takes data, returns data and never
touches a database, a socket or a file. The runners in ``eval.runners`` build
the data; the functions here only measure it.

The module imports nothing from another agent's package, so it works on its
own. The unit conversion uses ``pint`` when it is installed and falls back to
a small built-in table otherwise.

Vocabulary
----------
prediction
    A value the system produced for one ``(part_id, param_name)`` pair.
gold
    A value a person checked in the datasheet for the same pair.
match
    The prediction equals the gold value after the units are converted, within
    a relative tolerance (5 % by default) or an absolute tolerance for tiny
    values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = [
    "DEFAULT_ABS_TOLERANCE",
    "DEFAULT_TOLERANCE",
    "EvalRow",
    "UnitError",
    "Value",
    "accuracy_by_field",
    "accuracy_by_manufacturer",
    "build_rows",
    "confusion",
    "cost_per_datasheet",
    "field_accuracy",
    "latency_stats",
    "mrr",
    "normalise_value",
    "precision_at_k",
    "recall",
    "refusal_rate",
    "values_match",
]

#: Default relative tolerance for a value comparison (5 %).
DEFAULT_TOLERANCE = 0.05
#: Default absolute tolerance. It covers values that are tiny or exactly zero.
DEFAULT_ABS_TOLERANCE = 1e-9


class UnitError(ValueError):
    """Raised when a unit cannot be parsed or converted."""


# --------------------------------------------------------------------------------------
# Value model
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Value:
    """A numeric value with an optional unit."""

    value: float | None
    unit: str | None = None

    @property
    def missing(self) -> bool:
        """Return ``True`` when the value is absent."""
        return self.value is None


@dataclass
class EvalRow:
    """One scored ``(part, parameter)`` pair.

    ``predicted`` is ``None`` when the system did not produce the value. A
    missing prediction is a wrong prediction for the accuracy metric.
    """

    part_id: str
    param: str
    predicted: Value | None = None
    gold: Value | None = None
    manufacturer: str = ""
    family: str = ""
    method: str = ""
    status: str = ""
    refused: bool = False

    def is_correct(
        self, tolerance: float = DEFAULT_TOLERANCE, abs_tolerance: float = DEFAULT_ABS_TOLERANCE
    ) -> bool:
        """Return ``True`` when the prediction matches the gold value."""
        if self.predicted is None or self.gold is None:
            return False
        return values_match(
            self.predicted, self.gold, tolerance=tolerance, abs_tolerance=abs_tolerance
        )


# --------------------------------------------------------------------------------------
# Unit handling
# --------------------------------------------------------------------------------------

# Fallback conversion table. It is only used when ``pint`` is not installed.
_FALLBACK_UNITS: dict[str, tuple[float, str]] = {
    "v": (1.0, "V"),
    "mv": (1e-3, "V"),
    "kv": (1e3, "V"),
    "a": (1.0, "A"),
    "ma": (1e-3, "A"),
    "ua": (1e-6, "A"),
    "na": (1e-9, "A"),
    "ohm": (1.0, "ohm"),
    "mohm": (1e-3, "ohm"),
    "kohm": (1e3, "ohm"),
    "uohm": (1e-6, "ohm"),
    "w": (1.0, "W"),
    "mw": (1e-3, "W"),
    "degc": (1.0, "degC"),
    "c": (1.0, "degC"),
    "k": (1.0, "degC"),
    "f": (1.0, "F"),
    "uf": (1e-6, "F"),
    "nf": (1e-9, "F"),
    "pf": (1e-12, "F"),
    "h": (1.0, "H"),
    "uh": (1e-6, "H"),
    "nh": (1e-9, "H"),
    "s": (1.0, "s"),
    "ms": (1e-3, "s"),
    "us": (1e-6, "s"),
    "hz": (1.0, "Hz"),
    "khz": (1e3, "Hz"),
    "mhz": (1e6, "Hz"),
    "m": (1.0, "m"),
    "mm": (1e-3, "m"),
    "j": (1.0, "J"),
    "mj": (1e-3, "J"),
    "nc": (1e-9, "C"),
    "uc": (1e-6, "C"),
    "mc": (1e-3, "C"),
    "pc": (1e-12, "C"),
}

try:  # pragma: no cover - the fallback is exercised only without pint.
    import pint as _pint

    _REGISTRY = _pint.UnitRegistry()
    _CANONICAL_BY_DIMENSION: dict[str, str] = {
        str(_REGISTRY.parse_expression(canon).dimensionality): canon
        for canon in ("V", "A", "ohm", "degC", "F", "J", "W", "H", "Hz", "s", "m", "C", "N", "Pa")
    }
except Exception:  # pragma: no cover
    _pint = None  # type: ignore[assignment]
    _REGISTRY = None
    _CANONICAL_BY_DIMENSION = {}


def _canonical_from_pint(unit: str) -> tuple[str, str] | None:
    """Return ``(canonical_unit, factor)`` for ``unit`` using pint."""
    if _REGISTRY is None:
        return None
    try:
        quantity = _REGISTRY.parse_expression(unit)
    except Exception as exc:  # noqa: BLE001 - pint raises several error types
        raise UnitError(f"unknown unit: {unit!r}") from exc
    dimensionality = str(quantity.dimensionality)
    canonical = _CANONICAL_BY_DIMENSION.get(dimensionality)
    if canonical is None:
        return None
    return canonical, 1.0


def normalise_value(value: float | None, unit: str | None) -> tuple[float | None, str | None]:
    """Convert ``value`` to the canonical unit of its dimension.

    The canonical units are the SI base units of the dimension: ``V``, ``A``,
    ``ohm``, ``degC``, ``F``, ``J``, ``W``, ``H``, ``Hz``, ``s``, ``m``, ``C``,
    ``N`` and ``Pa``. A value without a unit stays dimensionless.

    The function raises :class:`UnitError` when the unit cannot be parsed.

    Returns:
        A tuple ``(value, canonical_unit)``. ``value`` is ``None`` when the
        input value was ``None``.
    """
    if value is None:
        return None, unit
    number = float(value)
    if unit is None:
        return number, None
    text = str(unit).strip()
    if text == "" or text == "1":
        return number, None
    if _REGISTRY is not None:
        try:
            quantity = _REGISTRY.Quantity(number, text)
        except Exception as exc:  # noqa: BLE001 - pint raises several error types
            raise UnitError(f"unknown unit: {unit!r}") from exc
        dimensionality = str(quantity.dimensionality)
        canonical = _CANONICAL_BY_DIMENSION.get(dimensionality)
        if canonical is None:
            return number, text
        return float(quantity.to(canonical).magnitude), canonical
    entry = _FALLBACK_UNITS.get(text.lower())
    if entry is None:
        raise UnitError(f"unknown unit: {unit!r}")
    factor, canonical = entry
    return number * factor, canonical


def _to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def values_match(
    a: Any,
    b: Any,
    tolerance: float = DEFAULT_TOLERANCE,
    abs_tolerance: float = DEFAULT_ABS_TOLERANCE,
    allow_missing_unit: bool = False,
) -> bool:
    """Return ``True`` when two values are the same after the unit conversion.

    ``a`` and ``b`` may be a :class:`Value`, a ``(value, unit)`` tuple, a
    number or ``None``.

    Two values match when the relative difference is at most ``tolerance`` or
    the absolute difference is at most ``abs_tolerance``. The relative test
    uses the larger magnitude of the two values, so the test is symmetric.
    """
    left = _coerce_value(a)
    right = _coerce_value(b)
    if left is None or right is None:
        return False
    if left.value is None or right.value is None:
        return False

    try:
        left_value, left_unit = normalise_value(left.value, left.unit)
        right_value, right_unit = normalise_value(right.value, right.unit)
    except UnitError:
        # Fall back to a plain comparison when both sides use the same unit
        # string. Different unit strings that cannot be parsed never match.
        if (left.unit or "").lower() != (right.unit or "").lower():
            return False
        left_value, left_unit = left.value, left.unit
        right_value, right_unit = right.value, right.unit

    if left_value is None or right_value is None:
        return False

    if left_unit != right_unit:
        if not allow_missing_unit:
            return False
        if left_unit not in (None, "") or right_unit not in (None, ""):
            return False

    scale = max(abs(left_value), abs(right_value))
    limit = abs_tolerance if scale == 0 else max(abs_tolerance, tolerance * scale)
    return abs(left_value - right_value) <= limit


# --------------------------------------------------------------------------------------
# Coercion helpers
# --------------------------------------------------------------------------------------


def _coerce_value(obj: Any) -> Value | None:
    """Convert any supported input into a :class:`Value`."""
    if obj is None:
        return None
    if isinstance(obj, Value):
        return obj
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return Value(float(obj), None)
    if isinstance(obj, str):
        number = _to_number(obj.strip())
        return None if number is None else Value(number, None)
    if isinstance(obj, Mapping):
        raw = obj.get("value")
        if raw is None:
            for key in ("value_typ", "value_max", "value_min"):
                if obj.get(key) is not None:
                    raw = obj[key]
                    break
        number = _to_number(raw)
        if number is None:
            return None
        unit = obj.get("unit")
        return Value(number, None if unit is None else str(unit))
    raw = getattr(obj, "value", None)
    if raw is None:
        for key in ("value_typ", "value_max", "value_min"):
            candidate = getattr(obj, key, None)
            if candidate is not None:
                raw = candidate
                break
    number = _to_number(raw)
    if number is None:
        return None
    unit = getattr(obj, "unit", None)
    return Value(number, None if unit is None else str(unit))


def _part_and_param(item: Any) -> tuple[str, str]:
    if isinstance(item, Mapping):
        part = item.get("part_id") or item.get("mpn") or ""
        param = item.get("param") or item.get("param_name") or item.get("name") or ""
        return str(part), str(param)
    part = getattr(item, "part_id", "") or getattr(item, "mpn", "") or ""
    param = (
        getattr(item, "param", None)
        or getattr(item, "param_name", None)
        or getattr(item, "name", "")
        or ""
    )
    return str(part), str(param)


def _pairs_from(obj: Any, attr: str = "predicted") -> dict[tuple[str, str], Value]:
    """Build a ``{(part_id, param): Value}`` mapping from any supported input."""
    out: dict[tuple[str, str], Value] = {}
    if obj is None:
        return out
    if isinstance(obj, Mapping):
        for key, raw in obj.items():
            if isinstance(key, tuple) and len(key) == 2:
                part, param = str(key[0]), str(key[1])
            elif isinstance(key, str) and ":" in key:
                part, param = key.split(":", 1)
            else:
                part, param = str(key), ""
            coerced = _coerce_value(raw)
            if coerced is not None:
                out[(part, param)] = coerced
        return out
    if isinstance(obj, (str, bytes)):
        return out
    if isinstance(obj, Iterable):
        for item in obj:
            if isinstance(item, EvalRow):
                part, param = item.part_id, item.param
                raw = item.predicted if attr == "predicted" else item.gold
            else:
                part, param = _part_and_param(item)
                if isinstance(item, Mapping):
                    raw = item.get(attr)
                    if (
                        raw is None
                        and "value" in item
                        and "gold" not in item
                        and "predicted" not in item
                    ):
                        raw = item.get("value")
                else:
                    raw = getattr(item, attr, None)
            coerced = _coerce_value(raw)
            if coerced is not None:
                out[(part, param)] = coerced
        return out
    coerced = _coerce_value(obj)
    if coerced is not None:
        out[("", "")] = coerced
    return out


def build_rows(predictions: Any, gold: Any) -> list[EvalRow]:
    """Pair the predictions with the gold values.

    The result holds one row per gold ``(part, parameter)`` pair. A pair
    without a prediction is a row with ``predicted=None``, so it counts as a
    wrong value in the accuracy metric.
    """
    gold_pairs = _pairs_from(gold, "gold")
    predicted_pairs = _pairs_from(predictions, "predicted")

    manufacturers: dict[str, str] = {}
    families: dict[str, str] = {}
    _collect_labels(predictions, manufacturers, families)
    _collect_labels(gold, manufacturers, families)

    rows: list[EvalRow] = []
    for (part, param), gold_value in gold_pairs.items():
        rows.append(
            EvalRow(
                part_id=part,
                param=param,
                predicted=predicted_pairs.get((part, param)),
                gold=gold_value,
                manufacturer=manufacturers.get(part, ""),
                family=families.get(part, ""),
            )
        )
    return rows


def _collect_labels(obj: Any, manufacturers: dict[str, str], families: dict[str, str]) -> None:
    if obj is None or isinstance(obj, (str, bytes)):
        return
    items: Iterable[Any]
    if isinstance(obj, Mapping):
        items = obj.values()
    elif isinstance(obj, Iterable):
        items = obj
    else:
        return
    for item in items:
        if isinstance(item, Mapping):
            part = str(item.get("part_id") or item.get("mpn") or "")
            manufacturer = item.get("manufacturer")
            family = item.get("family")
        else:
            part = str(getattr(item, "part_id", "") or getattr(item, "mpn", "") or "")
            manufacturer = getattr(item, "manufacturer", None)
            family = getattr(item, "family", None)
        if not part:
            continue
        if manufacturer:
            manufacturers.setdefault(part, str(manufacturer))
        if family:
            families.setdefault(part, str(family))


# --------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------


def field_accuracy(
    predictions: Any,
    gold: Any,
    tolerance: float = DEFAULT_TOLERANCE,
    abs_tolerance: float = DEFAULT_ABS_TOLERANCE,
) -> float:
    """Return the share of gold pairs that the prediction gets right.

    The denominator is the number of gold ``(part, parameter)`` pairs. A pair
    without a prediction counts as wrong. A pair with a wrong unit counts as
    wrong.

    Returns:
        A float between ``0.0`` and ``1.0``. An empty gold set gives ``0.0``.
    """
    rows = build_rows(predictions, gold)
    if not rows:
        return 0.0
    correct = sum(1 for row in rows if row.is_correct(tolerance, abs_tolerance))
    return correct / len(rows)


def _item_id(item: Any) -> str:
    """Return the identifier of a ranked item."""
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        for key in ("part_id", "mpn", "id", "alternative_id"):
            if item.get(key):
                return str(item[key])
        part = item.get("part")
        if part is not None:
            return _item_id(part)
        return ""
    for key in ("part_id", "mpn", "id", "alternative_id"):
        value = getattr(item, key, None)
        if value:
            return str(value)
    part = getattr(item, "part", None)
    if part is not None:
        return _item_id(part)
    return str(item)


def precision_at_k(retrieved: Sequence[Any], relevant: Iterable[Any], k: int = 3) -> float:
    """Return the share of the first ``k`` results that is relevant.

    The denominator is ``k``, so a short result list gives a lower value.
    """
    if k <= 0:
        return 0.0
    wanted = {_item_id(item) for item in relevant}
    if not wanted:
        return 0.0
    hits = 0
    for item in list(retrieved)[:k]:
        if _item_id(item) in wanted:
            hits += 1
    return hits / k


def recall(retrieved: Sequence[Any], relevant: Iterable[Any]) -> float:
    """Return the share of the relevant items that the result list contains."""
    wanted = {_item_id(item) for item in relevant}
    if not wanted:
        return 0.0
    found = {_item_id(item) for item in retrieved} & wanted
    return len(found) / len(wanted)


def mrr(ranked: Sequence[Any], relevant: Iterable[Any]) -> float:
    """Return the reciprocal rank of the first relevant item."""
    wanted = {_item_id(item) for item in relevant}
    if not wanted:
        return 0.0
    for position, item in enumerate(list(ranked)[: len(wanted) + 50], start=1):
        if _item_id(item) in wanted:
            return 1.0 / position
    return 0.0


def mean_reciprocal_rank(
    ranked_lists: Sequence[Sequence[Any]], relevant_lists: Sequence[Iterable[Any]]
) -> float:
    """Return the mean reciprocal rank over many queries."""
    scores = [
        mrr(ranked, relevant)
        for ranked, relevant in zip(ranked_lists, relevant_lists, strict=False)
    ]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _is_refused(record: Any) -> bool:
    if isinstance(record, bool):
        return record
    if isinstance(record, Mapping):
        for key in ("refused", "no_answer", "abstained"):
            if key in record:
                return bool(record[key])
        return False
    for key in ("refused", "no_answer", "abstained"):
        value = getattr(record, key, None)
        if value is not None:
            return bool(value)
    return False


def refusal_rate(results: Sequence[Any], refusals: Sequence[Any] | None = None) -> float:
    """Return the share of questions that the system refused to answer.

    ``results`` is the list of question records. A record may be a boolean
    (``True`` means refused), a mapping with a ``refused`` key or an object
    with a ``refused`` attribute.

    ``refusals`` is optional. When it is given it is the list of refused
    questions. It may be a list of indices into ``results``, a list of
    question identifiers, or a boolean mask with the same length as
    ``results``. When it is ``None`` the flags inside ``results`` are used.
    """
    total = len(list(results))
    if total == 0:
        return 0.0
    if refusals is None:
        refused = sum(1 for record in results if _is_refused(record))
        return refused / total

    mask = list(refusals)
    if len(mask) == total and all(isinstance(item, bool) for item in mask):
        return sum(1 for item in mask if item) / total
    identifiers = {_item_id(item) if not isinstance(item, int) else str(item) for item in mask}
    records = list(results)
    refused = 0
    for index, record in enumerate(records):
        if str(index) in identifiers or _item_id(record) in identifiers:
            refused += 1
    return refused / total


def _cost_of(record: Any) -> float:
    if isinstance(record, Mapping):
        for key in ("cost", "llm_cost", "cost_usd", "total_cost"):
            if record.get(key) is not None:
                value = _to_number(record[key])
                if value is not None:
                    return value
        return 0.0
    value = _to_number(getattr(record, "cost", None))
    return 0.0 if value is None else value


def _datasheet_of(record: Any) -> str:
    if isinstance(record, Mapping):
        for key in ("datasheet_id", "source_id", "pdf_id", "document_id"):
            if record.get(key):
                return str(record[key])
        return ""
    for key in ("datasheet_id", "source_id", "pdf_id", "document_id"):
        value = getattr(record, key, None)
        if value:
            return str(value)
    return ""


def cost_per_datasheet(calls: Any) -> float:
    """Return the average LLM cost of one datasheet.

    ``calls`` is a list of call records. Each record needs a ``cost`` and
    may carry a ``datasheet_id`` (or ``source_id``). When the records name
    their datasheet, the cost is divided by the number of distinct
    datasheets. When they do not, the cost is divided by the number of calls.

    ``calls`` may also be a mapping of ``datasheet_id`` to a list of records.
    """
    total_cost = 0.0
    datasheets: set[str] = set()
    call_count = 0

    if isinstance(calls, Mapping):
        for key, records in calls.items():
            datasheets.add(str(key))
            for record in records if isinstance(records, Iterable) else [records]:
                total_cost += _cost_of(record)
                call_count += 1
    else:
        for record in calls if isinstance(calls, Iterable) else []:
            total_cost += _cost_of(record)
            call_count += 1
            name = _datasheet_of(record)
            if name:
                datasheets.add(name)

    divisor = len(datasheets) if datasheets else call_count
    if divisor == 0:
        return 0.0
    return total_cost / divisor


def latency_stats(durations_ms: Iterable[float]) -> dict[str, float]:
    """Return the mean, the median and the p95 of the durations in ms.

    The result also holds the count, the minimum and the maximum.
    """
    values = [float(item) for item in durations_ms if item is not None]
    if not values:
        return {"count": 0, "mean": 0.0, "median": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "min": float(array.min()),
        "max": float(array.max()),
    }


_WRONG_LABELS = {"wrong", "invalid", "incorrect", "error", "false", "mismatch", "bad"}
_STOPPED_LABELS = {
    "rejected",
    "review",
    "stopped",
    "blocked",
    "quarantined",
    "invalid",
    "false",
    "wrong",
}


def confusion(true_labels: Sequence[Any], predicted_labels: Sequence[Any]) -> dict[str, Any]:
    """Return the confusion matrix of a binary decision.

    The function is used for the validation experiment. The truth label is
    ``wrong`` for a value that does not match the gold value. The predicted
    label is ``stopped`` when the validator rejected the value or sent it to
    the review queue.

    The result holds the full label matrix and the four binary counts.
    """
    truths = [str(label).strip().lower() for label in true_labels]
    predictions = [str(label).strip().lower() for label in predicted_labels]
    if len(truths) != len(predictions):
        raise ValueError("true_labels and predicted_labels must have the same length")

    labels = sorted(set(truths) | set(predictions))
    index = {label: position for position, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for truth, prediction in zip(truths, predictions, strict=True):
        matrix[index[truth]][index[prediction]] += 1

    true_positive = 0
    false_negative = 0
    false_positive = 0
    true_negative = 0
    for truth, prediction in zip(truths, predictions, strict=True):
        is_wrong = truth in _WRONG_LABELS
        is_stopped = prediction in _STOPPED_LABELS
        if is_wrong and is_stopped:
            true_positive += 1
        elif is_wrong:
            false_negative += 1
        elif is_stopped:
            false_positive += 1
        else:
            true_negative += 1

    total = len(truths)
    correct = sum(
        1 for truth, prediction in zip(truths, predictions, strict=True) if truth == prediction
    )
    return {
        "labels": labels,
        "matrix": matrix,
        "total": total,
        "correct": correct,
        "accuracy": (correct / total) if total else 0.0,
        "wrong_stopped": true_positive,
        "wrong_missed": false_negative,
        "false_alarms": false_positive,
        "correct_accepted": true_negative,
        "stop_rate": (
            (true_positive / (true_positive + false_negative))
            if (true_positive + false_negative)
            else 0.0
        ),
        "stop_precision": (
            (true_positive / (true_positive + false_positive))
            if (true_positive + false_positive)
            else 0.0
        ),
    }


# --------------------------------------------------------------------------------------
# Grouped accuracy
# --------------------------------------------------------------------------------------


def _groups(results: Any, key: str) -> dict[str, dict[str, float]]:
    """Group the scored results and count the correct ones per group."""
    groups: dict[str, dict[str, float]] = {}

    def add(name: str, correct: bool) -> None:
        bucket = groups.setdefault(name or "unknown", {"correct": 0.0, "total": 0.0})
        bucket["total"] += 1.0
        if correct:
            bucket["correct"] += 1.0

    if results is None:
        return groups

    if isinstance(results, Mapping):
        for name, payload in results.items():
            if isinstance(payload, Mapping) and "total" in payload:
                total = float(payload.get("total", 0.0))
                correct = float(payload.get("correct", 0.0))
                groups[str(name)] = {"correct": correct, "total": total}
            elif isinstance(payload, (int, float)):
                add(str(name), bool(payload))
            else:
                for item in payload:
                    add(str(name), _is_correct_item(item))
        return groups

    for item in results:
        if isinstance(item, EvalRow):
            name = item.manufacturer if key == "manufacturer" else item.param
            add(name or "unknown", item.is_correct())
        elif isinstance(item, Mapping):
            name = item.get(key)
            if name is None:
                name = item.get("param") if key == "field" else item.get("manufacturer")
            if "correct" in item:
                add(str(name or "unknown"), bool(item["correct"]))
            elif "matched" in item:
                add(str(name or "unknown"), bool(item["matched"]))
            elif "is_correct" in item:
                add(str(name or "unknown"), bool(item["is_correct"]))
            else:
                gold = item.get("gold", item.get("gold_value"))
                predicted = item.get("predicted", item.get("predicted_value"))
                add(str(name or "unknown"), values_match(gold, predicted))
        elif isinstance(item, (tuple, list)) and len(item) == 3:
            name, _param, correct = item
            add(str(name or "unknown"), bool(correct))
        else:
            add("unknown", _is_correct_item(item))
    return groups


def _is_correct_item(item: Any) -> bool:
    if isinstance(item, EvalRow):
        return item.is_correct()
    if isinstance(item, Mapping):
        if "correct" in item:
            return bool(item["correct"])
        gold = item.get("gold", item.get("gold_value"))
        predicted = item.get("predicted", item.get("predicted_value"))
        return values_match(gold, predicted)
    return bool(item)


def accuracy_breakdown(results: Any, key: str = "manufacturer") -> dict[str, dict[str, float]]:
    """Return the accuracy, the correct count and the total per group.

    ``key`` is ``"manufacturer"`` or ``"field"``.
    """
    groups = _groups(results, key)
    breakdown: dict[str, dict[str, float]] = {}
    for name, bucket in groups.items():
        total = bucket["total"]
        correct = bucket["correct"]
        breakdown[name] = {
            "accuracy": (correct / total) if total else 0.0,
            "correct": correct,
            "total": total,
        }
    return breakdown


def accuracy_by_manufacturer(results: Any) -> dict[str, float]:
    """Return the field accuracy for each manufacturer."""
    return {
        name: bucket["accuracy"]
        for name, bucket in accuracy_breakdown(results, "manufacturer").items()
    }


def accuracy_by_field(results: Any) -> dict[str, float]:
    """Return the field accuracy for each parameter name."""
    return {
        name: bucket["accuracy"] for name, bucket in accuracy_breakdown(results, "field").items()
    }
