# HANDOFF - tier 1 (rule based extraction)

Agent: **b-tier1** - branch `agent/b-tier1`
Plan: WP3, FR-03, FR-04, FR-05, FR-06

## What exists

```
backend/extraction/tier1/
  __init__.py      public API of the package
  page_finder.py   find_pages() - the pages that hold the characteristics tables
  tables.py        extract_tables() - pdfplumber tables as a normalised grid
  rows.py          table schema detection (which column is min/typ/max/...) + row parsing
  namemap.py       symbol/label -> standard name, fuzzy fallback, injectable lookup
  parsing.py       number / value cell / unit / condition parsing
  scanned.py       image only PDF detection (PyMuPDF)
  extractor.py     PdfTier1Extractor - assembles the ExtractionResult
backend/tests/tier1/
  conftest.py, test_parsing.py, test_namemap.py, test_tables.py,
  test_scanned.py, test_extractor.py
```

## Public API

```python
from extraction.tier1 import PdfTier1Extractor, NameMap
from shared.schemas import Family

extractor = PdfTier1Extractor(source_id="pdf-123")          # optional
result = extractor.extract("datasheet.pdf", Family.MOSFET)    # -> ExtractionResult
pages = extractor.find_pages("datasheet.pdf")                 # -> [1, 2]
```

`PdfTier1Extractor` implements the frozen protocol `Tier1Extractor`
(`backend/shared/interfaces.py`):

* `extract(pdf_path, family=None, *, source_id=None, part_id=None) -> ExtractionResult`
  (`method=ExtractionMethod.TIER1`; the two keyword arguments are additions,
  allowed by the interface rules).
* `find_pages(pdf_path) -> list[int]` - 1-based page numbers, document order,
  no duplicates.

Constructor:

```python
PdfTier1Extractor(name_map: NameMap | None = None, *, source_id=None, fuzzy_threshold=90.0)
```

`NameMap(lookup=callable)` makes the **lookup callable the authority** for the
name mapping (this is how the database agent injects its `name_map` table):

```python
def lookup(raw_name: str) -> str | None: ...     # -> "rds_on"
extractor = PdfTier1Extractor(name_map=NameMap(lookup))
```

Two helpers build that callable from the database export:

```python
from extraction.tier1 import load_name_map, lookup_from_rows

lookup = load_name_map("backend/db/seed_data/name_map.json")   # {"name_map": [...]}
lookup = lookup_from_rows([{"raw_name": "Qrr", "standard_name": "reverse_recovery_qrr"}])
```

A row may carry two standard names (`"supply_voltage_min,supply_voltage_max"`)
for a row that holds a range.

Helpers that other agents may reuse:

| function | purpose |
| --- | --- |
| `extraction.tier1.find_pages(pdf)` | pages with characteristics tables |
| `extraction.tier1.extract_tables(pdf, pages)` | tables as `ExtractedTable(page, rows)` |
| `extraction.tier1.detect_schema(rows)` | column roles of a table |
| `extraction.tier1.parse_row(row, schema, page)` | one row -> `ParsedRow` |
| `extraction.tier1.match_name(label, symbol=..., family=...)` | standard name(s) |
| `extraction.tier1.parse_value_cell(cell)` | `(min, typ, max)` + comparator |
| `extraction.tier1.parse_unit(cell)` | `(canonical pint unit, scale)` |
| `extraction.tier1.parse_condition(cell)` | `{"Vgs": "10 V", ...}` |
| `extraction.tier1.is_scanned(pdf)` | image only PDF |

## How to run

```bash
cd backend
.venv/bin/python -m pytest -q          # all green (tier 1 + the other agents)
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .
.venv/bin/python -m pytest tests/tier1  # only the tier-1 tests (120 tests)
```

No network access, no LLM call, no secret: the tests read the recorded
fixtures in `contracts/fixtures/` only.

## What the extractor does

1. **Scanned check** (`scanned.py`, PyMuPDF): fewer than 20 characters of
   text per page -> `scanned=True`, **no values at all**, `notes` says that
   tier 3 (vision) is needed.
2. **Page finder** (`page_finder.py`): a page is kept when it carries
   "electrical characteristics", "absolute maximum ratings", "characteristics",
   "maximum ratings", "absolute maximum", "electrical specifications" or
   "key specifications", or when it mentions the part number (PDF title, else
   the first MPN-like line of page 1).
3. **Tables** (`tables.py`): pdfplumber `extract_tables()` (ruled); when a
   page has no ruled table the `"text"` strategy is used as a fallback.
4. **Rows** (`rows.py`): the header row is detected ("Parameter", "Symbol",
   "Min", "Typ", "Max", "Unit", "Conditions", ...). A single "Min Typ Max"
   cell is supported as well. Each row becomes a `ParsedRow` with label,
   symbol, values, unit, conditions and the raw text.
5. **Names** (`namemap.py`): injected lookup -> exact symbol -> exact label ->
   rapidfuzz fallback (score >= 90 and unambiguous, confidence 0.70). A row
   that does not match is skipped **silently** and never becomes a value.
6. **Values** (`extractor.py`): every value carries `source_id`, `page`,
   `method=TIER1`, `condition`, `raw_text`, `value_text`, a confidence
   (0.85 base, lower for a fuzzy match / a bound / a missing unit) and
   `status=REVIEW` (the validator decides the final status).
   * A row with a min and a max ("Supply Voltage 4.5 ... 35 V") produces
     **two** values (`supply_voltage_min`, `supply_voltage_max`); the same
     holds for "Operating Temperature -40 ... 125 C".
   * `package` is a text value: `value=None`, `unit=None`, `value_text` holds
     the package name.
   * The first occurrence of a name wins (document order); a later row with
     the same name (e.g. the absolute maximum page) does not overwrite it.
   * `failed_fields` lists the family fields that could not be read (the
     standard names come from `MosfetSpec` / `GateDriverSpec`, so the two
     lists cannot drift apart).

## Known gaps / assumptions

* **Unit normalisation** - tier 1 is the *source layer*: it stores the unit
  exactly as the datasheet prints it (canonicalised in spelling only):
  `mOhm -> mohm`, `nC -> nC`, `pF -> pF`, `ns -> ns`, `C -> degC`,
  `C/W -> degC/W`. The units that the frozen fixture does not exercise are
  converted to the canonical base unit right away (`mV -> V` x 0.001,
  `uC -> C` x 1e-6, `nF -> F` x 1e-9, `us -> s` x 1e-6, `kOhm -> ohm` x 1000).
  This follows the "one canonical unit convention" of `docs/CONTRACTS.md`
  (source layer keeps the datasheet unit, everything after the validator is
  canonical). See `docs/CHANGE_REQUESTS/b-tier1-1.md`.
* **`channel_count`** - the fixture expects `channel_count = 1` for the
  synthetic gate driver, but that PDF has no channel cell. Tier 1 derives it
  from the `IO+` / `IO-` symbol pair with confidence 0.5 and a note (see the
  change request).
* **Deduplication** - "first row wins". A datasheet that lists a rating on
  the absolute-maximum page *and* a typical value in the characteristics
  page keeps the first one it meets (page order).
* **Family inference** - when the caller does not pass a family it is
  inferred from the table content (aliases) and from the numbers of
  MOSFET-only / gate-driver-only names; when both families score equally the
  family stays `None` and no field scoping is applied.
* **Only ruled / text tables** are read. A table that is an image inside a
  PDF with a text layer is not recognised - tier 3 covers that case.
* **No caching, no downloading**: tier 1 only reads a local PDF path.
* `ParameterValue.value` follows `typ > max > min`; for a bound (`< 0.5`)
  `value` stays `None` and the bound is kept in `value_max` / `value_min`
  with the comparator in `value_text`.
