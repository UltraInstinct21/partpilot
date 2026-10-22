"""Loader, validator and agreement report for the PartPilot gold set.

The gold set is a CSV file. Each row holds one value that a person read in
the datasheet and checked. The plan (WP8) asks for 80 parts, at least five
manufacturers, 10 to 15 fields per part and a second check of 20 % of the
labels.

The file format is the one in ``contracts/fixtures/gold/gold_set_example.csv``
and in ``eval/gold_set_template.csv``.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "GOLD_SET_COLUMNS",
    "GoldRow",
    "GoldSetError",
    "agreement_rate",
    "inter_annotator_agreement",
    "load_gold_set",
    "validate_gold_set",
]

#: The columns of the gold set CSV, in order.
GOLD_SET_COLUMNS: tuple[str, ...] = (
    "part_id",
    "mpn",
    "manufacturer",
    "family",
    "param_name",
    "value",
    "unit",
    "condition",
    "labelled_by",
    "second_check_by",
    "agreement",
    "notes",
)

#: The values the ``agreement`` column may hold.
AGREEMENT_VALUES = ("yes", "no")


class GoldSetError(ValueError):
    """Raised when a gold set file cannot be loaded."""


@dataclass
class GoldRow:
    """One labelled value of the gold set."""

    part_id: str
    mpn: str = ""
    manufacturer: str = ""
    family: str = ""
    param_name: str = ""
    value: float = 0.0
    unit: str = ""
    condition: dict[str, Any] = field(default_factory=dict)
    labelled_by: str = ""
    second_check_by: str = ""
    agreement: str = ""
    notes: str = ""
    row_number: int = 0

    @property
    def double_checked(self) -> bool:
        """Return ``True`` when a second member checked this label."""
        return bool(self.second_check_by.strip())

    @property
    def agreed(self) -> bool:
        """Return ``True`` when the second member agreed with the label."""
        return self.agreement.strip().lower() == "yes"


def _parse_condition(raw: str) -> dict[str, Any]:
    """Parse the condition column. It holds a JSON object or free text."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {"text": text}
    if isinstance(parsed, dict):
        return parsed
    return {"text": text}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(
                {
                    key: ("" if value is None else value)
                    for key, value in row.items()
                    if key is not None
                }
            )
        return rows


def validate_gold_set(path: str | Path) -> list[str]:
    """Check the gold set file and return the list of problems.

    An empty list means that the file is valid. The checks are:

    * every column of :data:`GOLD_SET_COLUMNS` is in the header;
    * every ``value`` is a number;
    * every numeric row has a unit;
    * every ``(part_id, param_name)`` pair appears once;
    * every row has a ``labelled_by``;
    * every ``agreement`` is ``yes``, ``no`` or empty.
    """
    file_path = Path(path)
    problems: list[str] = []
    if not file_path.exists():
        return [f"the file {file_path} does not exist"]
    if not file_path.is_file():
        return [f"the path {file_path} is not a file"]

    with file_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return ["the file is empty"]
        body = list(reader)

    header = [column.strip() for column in header]
    missing = [column for column in GOLD_SET_COLUMNS if column not in header]
    if missing:
        problems.append(f"the header is missing the column(s): {', '.join(missing)}")

    index = {column: position for position, column in enumerate(header)}

    def cell(row: Sequence[str], column: str) -> str:
        position = index.get(column)
        if position is None or position >= len(row):
            return ""
        return row[position].strip()

    seen: dict[tuple[str, str], int] = {}
    for number, row in enumerate(body, start=2):
        if not any(part.strip() for part in row):
            continue
        part_id = cell(row, "part_id")
        param_name = cell(row, "param_name")
        raw_value = cell(row, "value")
        unit = cell(row, "unit")
        labelled_by = cell(row, "labelled_by")
        agreement = cell(row, "agreement").lower()

        if not part_id:
            problems.append(f"row {number}: part_id is empty")
        if not param_name:
            problems.append(f"row {number}: param_name is empty")
        if raw_value == "":
            problems.append(f"row {number}: the value is empty")
        else:
            try:
                float(raw_value)
            except ValueError:
                problems.append(f"row {number}: the value {raw_value!r} is not numeric")
            else:
                if not unit:
                    problems.append(
                        f"row {number}: the unit is missing for the numeric value {raw_value!r}"
                    )
        key = (part_id, param_name)
        if key in seen:
            problems.append(
                f"row {number}: the pair ({part_id}, {param_name}) is already used in row {seen[key]}"
            )
        else:
            seen[key] = number
        if not labelled_by:
            problems.append(f"row {number}: labelled_by is empty")
        if agreement not in ("", *AGREEMENT_VALUES):
            problems.append(f"row {number}: the agreement {agreement!r} must be yes, no or empty")

    return problems


def load_gold_set(path: str | Path, skip_invalid: bool = False) -> list[GoldRow]:
    """Load the gold set file into a list of :class:`GoldRow` objects.

    The file is validated first. When it has problems the function raises
    :class:`GoldSetError`, unless ``skip_invalid`` is ``True``. In that case
    the broken rows are skipped and the good rows are returned.
    """
    file_path = Path(path)
    problems = validate_gold_set(file_path)
    if problems and not skip_invalid:
        joined = "\n".join(f"  - {problem}" for problem in problems)
        raise GoldSetError(f"the gold set {file_path} is not valid:\n{joined}")

    rows: list[GoldRow] = []
    for number, raw in enumerate(_read_rows(file_path), start=2):
        if not raw.get("part_id", "").strip():
            continue
        try:
            value = float(raw.get("value", ""))
        except ValueError:
            if skip_invalid:
                continue
            raise GoldSetError(
                f"row {number}: the value {raw.get('value')!r} is not numeric"
            ) from None
        rows.append(
            GoldRow(
                part_id=raw.get("part_id", "").strip(),
                mpn=raw.get("mpn", "").strip(),
                manufacturer=raw.get("manufacturer", "").strip(),
                family=raw.get("family", "").strip(),
                param_name=raw.get("param_name", "").strip(),
                value=value,
                unit=raw.get("unit", "").strip(),
                condition=_parse_condition(raw.get("condition", "")),
                labelled_by=raw.get("labelled_by", "").strip(),
                second_check_by=raw.get("second_check_by", "").strip(),
                agreement=raw.get("agreement", "").strip().lower(),
                notes=raw.get("notes", "").strip(),
                row_number=number,
            )
        )
    return rows


def inter_annotator_agreement(rows: Iterable[GoldRow]) -> dict[str, Any]:
    """Return the agreement between the two members that labelled the set.

    Only the rows that a second member checked count towards the agreement
    rate. A row with a second checker but no ``agreement`` value counts as
    *not recorded*, not as a disagreement.

    The result holds the number of rows, the number of double checked rows,
    the share of double checked rows, the agreement rate and the counts.
    """
    all_rows = list(rows)
    total = len(all_rows)
    checked = [row for row in all_rows if row.double_checked]
    agreed = [row for row in checked if row.agreed]
    disagreed = [row for row in checked if row.agreement.strip().lower() == "no"]
    unrecorded = [row for row in checked if row.agreement.strip().lower() not in AGREEMENT_VALUES]
    recorded = agreed + disagreed

    by_labeller: dict[str, dict[str, int]] = {}
    for row in checked:
        bucket = by_labeller.setdefault(row.labelled_by or "unknown", {"checked": 0, "agreed": 0})
        bucket["checked"] += 1
        if row.agreed:
            bucket["agreed"] += 1

    agreement = len(agreed) / len(recorded) if recorded else 0.0
    return {
        "total_rows": total,
        "double_checked": len(checked),
        "double_checked_pct": (len(checked) / total) if total else 0.0,
        "recorded": len(recorded),
        "agreed": len(agreed),
        "disagreed": len(disagreed),
        "unrecorded": len(unrecorded),
        "agreement_rate": agreement,
        "by_labeller": by_labeller,
    }


def agreement_rate(rows: Iterable[GoldRow]) -> float:
    """Return only the agreement rate between the two members."""
    return float(inter_annotator_agreement(rows)["agreement_rate"])
