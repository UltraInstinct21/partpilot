"""Cell level parsing for tier 1 (numbers, units, conditions).

Everything in this module is pure and deterministic: it never looks at a PDF
and never invents a value.  A cell that cannot be read unambiguously yields
``None`` (or an all-``None`` :class:`ParsedValue`) - never a guess.

Owner: agent b-tier1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "ParsedValue",
    "extract_label_conditions",
    "extract_label_symbol",
    "extract_label_unit",
    "normalise_condition_key",
    "parse_condition",
    "parse_number",
    "parse_unit",
    "parse_value_cell",
]

# Cells that mean "not specified".  They are NOT zero (FR-06 / tier rules).
_NOT_SPECIFIED = {
    "",
    "-",
    "--",
    "---",
    "–",
    "—",
    "n/a",
    "na",
    "n.a.",
    "n.a",
    "?",
    "not applicable",
    "not specified",
}

_NUM_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

# Unit spellings -> (canonical pint unit, scale).  The scale is applied to the
# numeric value so that the stored value is expressed in the canonical unit.
#
# NOTE ON THE "mohm" / "nC" / "pF" / "ns" ROWS: the frozen fixture
# ``contracts/fixtures/pdfs/expected_values.json`` pins those four canonical
# units (rds_on -> "mohm" with value 5.5, total_gate_charge_qg -> "nC" with
# value 62, input_capacitance_ciss -> "pF" with value 4900,
# propagation_delay -> "ns" with value 20).  The scale is therefore 1.0 for
# them and the value is kept as printed.  Every other unit follows the
# normalisation table of the plan (mV -> V, uC -> C, nF -> F, ...).  See
# ``docs/CHANGE_REQUESTS/b-tier1-1.md``.
_UNIT_MAP: dict[str, tuple[str, float]] = {
    # voltage
    "v": ("V", 1.0),
    "volt": ("V", 1.0),
    "volts": ("V", 1.0),
    "mv": ("V", 1e-3),
    "millivolt": ("V", 1e-3),
    "kv": ("V", 1e3),
    "kilovolt": ("V", 1e3),
    # current
    "a": ("A", 1.0),
    "amp": ("A", 1.0),
    "amps": ("A", 1.0),
    "ampere": ("A", 1.0),
    "amperes": ("A", 1.0),
    "ma": ("A", 1e-3),
    "milliamp": ("A", 1e-3),
    "milliampere": ("A", 1e-3),
    "ua": ("A", 1e-6),
    "µa": ("A", 1e-6),
    "μa": ("A", 1e-6),
    "microampere": ("A", 1e-6),
    # power
    "w": ("W", 1.0),
    "watt": ("W", 1.0),
    "mw": ("W", 1e-3),
    "milliwatt": ("W", 1e-3),
    # resistance
    "ω": ("ohm", 1.0),
    "ohm": ("ohm", 1.0),
    "ohms": ("ohm", 1.0),
    "mohm": ("mohm", 1.0),
    "mω": ("mohm", 1.0),
    "milliohm": ("mohm", 1.0),
    "milliohms": ("mohm", 1.0),
    "uohm": ("ohm", 1e-6),
    "µohm": ("ohm", 1e-6),
    "μohm": ("ohm", 1e-6),
    "microohm": ("ohm", 1e-6),
    "kohm": ("ohm", 1e3),
    "kω": ("ohm", 1e3),
    "kiloohm": ("ohm", 1e3),
    # charge
    "c": ("degC", 1.0),
    "℃": ("degC", 1.0),
    "°c": ("degC", 1.0),
    "degc": ("degC", 1.0),
    "nc": ("nC", 1.0),
    "nanocoulomb": ("nC", 1.0),
    "uc": ("C", 1e-6),
    "µc": ("C", 1e-6),
    "μc": ("C", 1e-6),
    "microcoulomb": ("C", 1e-6),
    "mc": ("C", 1e-3),
    "millicoulomb": ("C", 1e-3),
    # capacitance
    "pf": ("pF", 1.0),
    "picofarad": ("pF", 1.0),
    "nf": ("F", 1e-9),
    "nanofarad": ("F", 1e-9),
    "uf": ("F", 1e-6),
    "µf": ("F", 1e-6),
    "μf": ("F", 1e-6),
    "microfarad": ("F", 1e-6),
    "mf": ("F", 1e-3),
    "millifarad": ("F", 1e-3),
    "f": ("F", 1.0),
    "farad": ("F", 1.0),
    # time
    "s": ("s", 1.0),
    "sec": ("s", 1.0),
    "second": ("s", 1.0),
    "ms": ("s", 1e-3),
    "millisecond": ("s", 1e-3),
    "us": ("s", 1e-6),
    "µs": ("s", 1e-6),
    "μs": ("s", 1e-6),
    "microsecond": ("s", 1e-6),
    "ns": ("ns", 1.0),
    "nanosecond": ("ns", 1.0),
    "ps": ("s", 1e-12),
    "picosecond": ("s", 1e-12),
    # thermal
    "c/w": ("degC/W", 1.0),
    "°c/w": ("degC/W", 1.0),
    "degc/w": ("degC/W", 1.0),
    "c/j": ("degC/W", 1.0),
    # dimensionless
    "%": ("%", 1.0),
    "percent": ("%", 1.0),
    "ppm": ("ppm", 1.0),
    "pcs": ("pcs", 1.0),
    "ea": ("pcs", 1.0),
}

# Trailing unit words that may sneak into a value cell ("175 C").
_TRAILING_UNIT_RE = re.compile(
    r"^(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*"
    r"(?P<unit>[A-Za-zµμΩω°%/]+(?:/[A-Za-zµμΩω°]+)?)$"
)

# Condition keys, normalised to the canonical spelling used by the project.
_CONDITION_KEYS: dict[str, str] = {
    "vgs": "Vgs",
    "vgs(th)": "Vgs",
    "vg": "Vg",
    "vds": "Vds",
    "vdd": "Vdd",
    "vcc": "Vcc",
    "vin": "Vin",
    "id": "Id",
    "i_d": "Id",
    "idc": "Id",
    "ij": "Id",
    "io": "Io",
    "io+": "Io",
    "io-": "Io",
    "tj": "Tj",
    "tc": "Tc",
    "ta": "Ta",
    "tamb": "Tamb",
    "t": "Tj",
    "rl": "Rl",
    "cl": "Cl",
    "f": "F",
    "freq": "F",
    "frequency": "F",
    "qg": "Qg",
    "qgd": "Qgd",
    "di/dt": "di/dt",
    "m": "M",
}

_COMPARATOR_RE = re.compile(r"^(?P<cmp><=|>=|<|>|~)\s*(?P<rest>.+)$")
_TOLERANCE_RE = re.compile(r"^±\s*(?P<rest>.+)$")
_QUALIFIER_RE = re.compile(r"\b(?P<qual>max|min|typ|typical)\b\.?$", re.IGNORECASE)
_RANGE_RE = re.compile(
    r"^(?P<lo>[^-\s][^\s]*)\s*(?:-|–|—|to|~)\s*(?P<hi>[^\s]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedValue:
    """The result of parsing one value cell.

    ``minimum`` / ``typical`` / ``maximum`` are ``None`` when the cell does not
    specify them.  ``comparator`` holds ``"<"``, ``">"``, ``"<="``, ``">="`` or
    ``"±"`` when the cell states a bound instead of a point value.
    """

    minimum: float | None = None
    typical: float | None = None
    maximum: float | None = None
    comparator: str | None = None
    qualifier: str | None = None
    raw: str = ""

    @property
    def is_bound(self) -> bool:
        """``True`` when the cell is a bound ("< 0.5"), not a point value."""
        return self.comparator in {"<", ">", "<=", ">="}

    @property
    def point(self) -> float | None:
        """The point value of the cell (``None`` for a bound)."""
        if self.is_bound:
            return None
        for candidate in (self.typical, self.maximum, self.minimum):
            if candidate is not None:
                return candidate
        return None

    @property
    def has_value(self) -> bool:
        return any(v is not None for v in (self.minimum, self.typical, self.maximum))


def clean_cell(text: str | None) -> str:
    """Normalise whitespace of a table cell."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).replace("\u00a0", " ")).strip()


def parse_number(text: str | None) -> float | None:
    """Parse a single number, robustly.

    Handles ``1.0e-3``, ``1,234`` (thousands), ``1 234`` (thousands) and
    ``5,5`` (decimal comma).  Returns ``None`` when the text is not a number.
    """
    raw = clean_cell(text)
    if not raw or raw.lower() in _NOT_SPECIFIED:
        return None
    candidate = raw.replace(" ", "")
    if candidate.endswith("%"):
        candidate = candidate[:-1]
    # thousands separator: 1,234 / 1,234,567
    if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", candidate):
        candidate = candidate.replace(",", "")
    # decimal comma: 5,5
    elif re.fullmatch(r"[+-]?\d+,\d+", candidate):
        candidate = candidate.replace(",", ".")
    if not _NUM_RE.fullmatch(candidate):
        return None
    try:
        return float(candidate)
    except ValueError:  # pragma: no cover - guarded by the regex above
        return None


def _split_list(text: str) -> list[str] | None:
    """Split a cell that holds several numbers (min / typ / max).

    Returns ``None`` when the cell is a single number.
    """
    if "/" in text:
        parts = [p.strip() for p in text.split("/") if p.strip()]
        if len(parts) >= 2:
            return parts
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) == 2:
            if all(re.fullmatch(r"\d{1,3}", p) for p in parts):
                return None  # thousands separator, not a list
            if ", " in text:
                return parts  # "2, 3.5" -> two values
            return None  # "5,5" -> decimal comma
        if len(parts) == 3:
            if all(re.fullmatch(r"\d{1,3}", p) for p in parts):
                return None  # thousands separator
            return parts
    return None


def parse_value_cell(text: str | None) -> ParsedValue:
    """Parse a value cell into minimum / typical / maximum.

    Examples::

        "5.5"                 -> typical = 5.5
        "2 / 3.5 / 4.5"       -> min 2, typ 3.5, max 4.5
        "2, 3.5, 4.5"         -> min 2, typ 3.5, max 4.5
        "-"                   -> nothing (not specified)
        "5.5 max"             -> typ = 5.5
        "< 0.5"               -> max = 0.5, comparator "<" (a bound)
        "> 100"               -> min = 100, comparator ">" (a bound)
        "10 - 100"            -> min 10, max 100
        "±5 %"                -> typ = 5, comparator "±"
    """
    raw = clean_cell(text)
    if raw.lower() in _NOT_SPECIFIED:
        return ParsedValue(raw=raw)

    comparator: str | None = None
    body = raw

    match = _COMPARATOR_RE.match(body)
    if match:
        comparator = match.group("cmp")
        body = match.group("rest").strip()

    tolerance = _TOLERANCE_RE.match(body)
    if tolerance:
        comparator = "±"
        body = tolerance.group("rest").strip()

    qualifier: str | None = None
    qual_match = _QUALIFIER_RE.search(body)
    if qual_match:
        qualifier = qual_match.group("qual").lower()
        body = body[: qual_match.start()].strip()

    # a trailing unit word: "175 C"
    unit_match = _TRAILING_UNIT_RE.match(body)
    if unit_match and parse_number(unit_match.group("num")) is not None:
        body = unit_match.group("num")

    # a range: "10 - 100"
    range_match = _RANGE_RE.match(body)
    if range_match:
        low = parse_number(range_match.group("lo"))
        high = parse_number(range_match.group("hi"))
        if low is not None and high is not None:
            low, high = min(low, high), max(low, high)
            return ParsedValue(
                minimum=low,
                maximum=high,
                comparator=comparator,
                qualifier=qualifier,
                raw=raw,
            )

    # several numbers in one cell
    parts = _split_list(body)
    if parts:
        numbers = [parse_number(p) for p in parts]
        if all(n is not None for n in numbers) and numbers:
            if len(numbers) == 2:
                low, high = min(numbers), max(numbers)  # type: ignore[type-var]
                return ParsedValue(
                    minimum=low,
                    maximum=high,
                    comparator=comparator,
                    qualifier=qualifier,
                    raw=raw,
                )
            return ParsedValue(
                minimum=numbers[0],
                typical=numbers[1],
                maximum=numbers[2],
                comparator=comparator,
                qualifier=qualifier,
                raw=raw,
            )

    number = parse_number(body)
    if number is None:
        return ParsedValue(raw=raw)

    if comparator in {"<", "<="}:
        return ParsedValue(maximum=number, comparator=comparator, qualifier=qualifier, raw=raw)
    if comparator in {">", ">="}:
        return ParsedValue(minimum=number, comparator=comparator, qualifier=qualifier, raw=raw)
    if comparator == "±":
        return ParsedValue(typical=number, comparator=comparator, qualifier=qualifier, raw=raw)
    return ParsedValue(typical=number, qualifier=qualifier, raw=raw)


def parse_unit(text: str | None) -> tuple[str | None, float]:
    """Parse a unit cell.

    Returns ``(canonical_unit, scale)``.  ``scale`` is the factor that has to
    be applied to the printed number to obtain the value in the canonical
    unit.  ``(None, 1.0)`` means "no unit in this cell".
    """
    raw = clean_cell(text)
    if not raw:
        return None, 1.0
    key = raw.replace(" ", "").replace("°", "°").lower()
    if key in _UNIT_MAP:
        return _UNIT_MAP[key]
    # a parenthesised unit: "(mOhm)" or "mOhm (min)"
    stripped = raw.strip("()[] ").replace(" ", "").lower()
    if stripped in _UNIT_MAP:
        return _UNIT_MAP[stripped]
    return None, 1.0


def normalise_condition_key(key: str) -> str:
    """Normalise a condition key ("VGS" -> "Vgs", "ID" -> "Id", ...)."""
    raw = clean_cell(key).strip("()[] ").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in _CONDITION_KEYS:
        return _CONDITION_KEYS[lowered]
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9/\-]*", raw):
        return raw[0].upper() + raw[1:].lower()
    return raw


def parse_condition(text: str | None) -> dict[str, str]:
    """Parse a conditions cell into a dictionary.

    ``"VGS = 10 V, ID = 10 A, TJ = 25 C"`` becomes
    ``{"Vgs": "10 V", "Id": "10 A", "Tj": "25 C"}``.
    """
    raw = clean_cell(text)
    if not raw:
        return {}
    result: dict[str, str] = {}
    for chunk in re.split(r"[;,|]", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
        elif ":" in chunk:
            key, value = chunk.split(":", 1)
        else:
            continue
        key = normalise_condition_key(key)
        value = clean_cell(value).strip(" .,;")
        if key and value:
            result[key] = value
    return result


_LABEL_TEMP_RE = re.compile(r"@\s*(?P<temp>-?\d+(?:\.\d+)?)\s*°?\s*C\b", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^()]*)\)")


def extract_label_conditions(label: str | None) -> dict[str, str]:
    """Read conditions that live inside a parameter label.

    ``"Continuous Drain Current (Id) @ 25°C"`` -> ``{"Tc": "25 C"}``.
    """
    raw = clean_cell(label)
    if not raw:
        return {}
    match = _LABEL_TEMP_RE.search(raw)
    if not match:
        return {}
    return {"Tc": f"{match.group('temp')} C"}


def extract_label_unit(label: str | None) -> tuple[str | None, float]:
    """Read a unit that lives inside a parameter label.

    ``"Drain-Source On-Resistance (mOhm)"`` -> ``("mohm", 1.0)``.
    """
    raw = clean_cell(label)
    if not raw:
        return None, 1.0
    for inner in _PAREN_RE.findall(raw):
        unit, scale = parse_unit(inner)
        if unit is not None:
            return unit, scale
    return None, 1.0


def extract_label_symbol(label: str | None) -> str | None:
    """Read a symbol that lives inside a parameter label, e.g. ``(Id)``."""
    raw = clean_cell(label)
    if not raw:
        return None
    for inner in _PAREN_RE.findall(raw):
        candidate = clean_cell(inner)
        if not candidate:
            continue
        if parse_unit(candidate)[0] is not None:
            continue  # it is a unit, not a symbol
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9()/\-]*", candidate):
            return candidate
    return None
