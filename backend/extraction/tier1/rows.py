"""Table schema detection and row parsing (tier 1).

Owner: agent b-tier1.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parsing import (
    ParsedValue,
    clean_cell,
    extract_label_conditions,
    extract_label_symbol,
    extract_label_unit,
    parse_condition,
    parse_unit,
    parse_value_cell,
)

__all__ = ["ParsedRow", "TableSchema", "detect_schema", "parse_row"]


@dataclass
class TableSchema:
    """The column roles of a characteristics table."""

    header_index: int | None = None
    param_col: int = 0
    symbol_col: int | None = 1
    min_col: int | None = None
    typ_col: int | None = None
    max_col: int | None = None
    mtm_col: int | None = None
    value_col: int | None = None
    unit_col: int | None = None
    conditions_col: int | None = None


def cell_role(cell: str) -> str | None:
    """Return the role of a header cell ("param", "symbol", "min", ...)."""
    text = clean_cell(cell).lower()
    if not text:
        return None
    if "min" in text and "typ" in text and "max" in text:
        return "mtm"
    if text.startswith(("param", "character", "property", "item", "description", "name")):
        return "param"
    if text.startswith("symbol"):
        return "symbol"
    if text.startswith("min"):
        return "min"
    if text.startswith("typ"):
        return "typ"
    if text.startswith("max"):
        return "max"
    if text.startswith(("value", "rating")):
        return "value"
    if text.startswith("unit"):
        return "unit"
    if text.startswith("condition"):
        return "conditions"
    if text.startswith(("comment", "note", "remark")):
        return "comment"
    return None


def detect_schema(rows: list[list[str]]) -> TableSchema:
    """Find the header row of a table and map its columns to roles."""
    for index, row in enumerate(rows):
        roles = [cell_role(cell) for cell in row]
        if "param" not in roles:
            continue
        schema = TableSchema(header_index=index)
        for col, role in enumerate(roles):
            if role == "param":
                schema.param_col = col
            elif role == "symbol":
                schema.symbol_col = col
            elif role == "min":
                schema.min_col = col
            elif role == "typ":
                schema.typ_col = col
            elif role == "max":
                schema.max_col = col
            elif role == "mtm":
                schema.mtm_col = col
            elif role == "value":
                schema.value_col = col
            elif role == "unit":
                schema.unit_col = col
            elif role == "conditions":
                schema.conditions_col = col
        if schema.symbol_col is None and schema.param_col == 0:
            schema.symbol_col = 1
        return schema
    return _fallback_schema(rows)


def _fallback_schema(rows: list[list[str]]) -> TableSchema:
    """Guess the layout of a table that has no recognisable header."""
    width = max((len(row) for row in rows), default=0)
    schema = TableSchema(header_index=None, param_col=0, symbol_col=1)
    if width >= 7:
        schema.min_col, schema.typ_col, schema.max_col = 2, 3, 4
        schema.unit_col, schema.conditions_col = 5, 6
    elif width == 6:
        schema.min_col, schema.typ_col, schema.max_col = 2, 3, 4
        schema.unit_col = 5
    elif width == 5:
        schema.value_col, schema.unit_col, schema.conditions_col = 2, 3, 4
    elif width == 4:
        schema.value_col, schema.unit_col = 2, 3
    elif width == 3:
        schema.value_col = 2
    return schema


@dataclass
class ParsedRow:
    """One parameter row of a characteristics table."""

    page: int
    label: str
    symbol: str | None
    values: ParsedValue
    promote_typical: bool
    unit: str | None
    unit_scale: float
    conditions: dict[str, str]
    raw: str
    value_text: str = ""


def _cell(row: list[str], col: int | None) -> str:
    if col is None or col >= len(row):
        return ""
    return clean_cell(row[col])


def parse_row(row: list[str], schema: TableSchema, page: int) -> ParsedRow | None:
    """Parse one table row into a :class:`ParsedRow` (``None`` for empty rows)."""
    label = _cell(row, schema.param_col)
    if not label:
        return None

    symbol = _cell(row, schema.symbol_col) or extract_label_symbol(label) or ""

    values = ParsedValue()
    promote_typical = False
    value_text = ""

    if schema.mtm_col is not None:
        value_text = _cell(row, schema.mtm_col)
        values = parse_value_cell(value_text)
        promote_typical = values.minimum is not None and values.maximum is not None
    elif schema.min_col is not None or schema.typ_col is not None or schema.max_col is not None:
        minimum = None
        typical = None
        maximum = None
        comparator = None
        min_cell = parse_value_cell(_cell(row, schema.min_col))
        typ_cell = parse_value_cell(_cell(row, schema.typ_col))
        max_cell = parse_value_cell(_cell(row, schema.max_col))
        if min_cell.comparator in {">", ">="}:
            minimum = min_cell.minimum
            comparator = min_cell.comparator
        elif min_cell.minimum is not None:
            minimum = min_cell.minimum
        elif not min_cell.is_bound:
            minimum = min_cell.point
        if max_cell.comparator in {"<", "<="}:
            maximum = max_cell.maximum
            comparator = max_cell.comparator
        elif max_cell.maximum is not None:
            maximum = max_cell.maximum
        elif not max_cell.is_bound:
            maximum = max_cell.point
        if typ_cell.typical is not None:
            typical = typ_cell.typical
        elif not typ_cell.is_bound and typ_cell.maximum is not None:
            typical = typ_cell.maximum
        elif not typ_cell.is_bound and typ_cell.minimum is not None:
            typical = typ_cell.minimum
        values = ParsedValue(
            minimum=minimum,
            typical=typical,
            maximum=maximum,
            comparator=comparator,
            raw=" | ".join(
                part
                for part in (
                    _cell(row, schema.min_col),
                    _cell(row, schema.typ_col),
                    _cell(row, schema.max_col),
                )
                if part
            ),
        )
        value_text = values.raw
        promote_typical = True
    elif schema.value_col is not None:
        value_text = _cell(row, schema.value_col)
        values = parse_value_cell(value_text)
        # A lone "Value" column is a rating, not a typical value: it is stored
        # as ``value`` only.  A cell that holds a range ("2 / 3.5 / 4.5") keeps
        # its min/typ/max.
        promote_typical = values.minimum is not None and values.maximum is not None

    unit, scale = parse_unit(_cell(row, schema.unit_col))
    if unit is None:
        unit, scale = extract_label_unit(label)

    conditions = parse_condition(_cell(row, schema.conditions_col))
    for key, value in extract_label_conditions(label).items():
        conditions.setdefault(key, value)

    raw = " | ".join(cell for cell in row if cell)

    return ParsedRow(
        page=page,
        label=label,
        symbol=symbol or None,
        values=values,
        promote_typical=promote_typical,
        unit=unit,
        unit_scale=scale,
        conditions=conditions,
        raw=raw,
        value_text=value_text,
    )
