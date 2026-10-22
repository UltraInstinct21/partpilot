# HANDOFF - agent E-data (data layer)

The persistence layer of PartPilot: SQLAlchemy models, the repository of the
frozen `PartsRepository` protocol, the schema management, the seed loader and
the tests.

---

## 1. What exists

| File | Purpose |
| --- | --- |
| `backend/db/models.py` | SQLAlchemy 2.x models (`DeclarativeBase`, `Mapped[...]`) for `parts`, `parameters`, `sources`, `offers`, `name_map`, `llm_calls`, `review_corrections`. Mirrors `backend/shared/db_schema.sql` exactly (column names, types, CHECK constraints, UNIQUE constraints, index names). |
| `backend/db/session.py` | Engine creation (`create_engine_for_url`, `create_engine_from_settings`, `create_memory_engine`), `session_scope()`, `init_db()`, `migrate()`, `apply_reference_schema()`, `parse_timestamp()`. |
| `backend/db/repository.py` | `SqlAlchemyPartsRepository` (the `PartsRepository` implementation) and `NameMapRepository`. |
| `backend/db/units.py` | Private pint helper: canonical units, `canonicalize()`, the unit->canonical scale map and the standard-name->unit registry. |
| `backend/db/seed.py` | Idempotent seed loader + `python -m db.seed` entry point. |
| `backend/db/seed_data/name_map.json` | Alias table (raw datasheet header -> standard name) that the seed loader loads into `name_map`. |
| `backend/db/migrations/0001_initial.sql` | The initial migration (a verbatim copy of the frozen reference schema). |
| `backend/tests/db/**` | 98 tests of the data layer (schema, CRUD, search, review, statistics, seed, name map, units, protocol). |

Nothing outside `backend/db/**` and `backend/tests/db/**` was touched.

---

## 2. Public API

```python
from db import (
    SqlAlchemyPartsRepository,   # the PartsRepository implementation
    NameMapRepository,           # the name_map table
    init_db,                     # create the schema
    migrate,                     # apply the pending migrations
    create_engine_for_url,       # engine
    create_engine_from_settings, # engine for Settings.database_url
    create_memory_engine,        # in-memory engine (tests)
    session_scope,               # unit of work
    load_seed,                   # idempotent seed loader
    Base,                        # the declarative base
    KEY_PARAMETERS,              # {family: (name, ...)} of the summary columns
)
```

### `SqlAlchemyPartsRepository(engine_or_session)`

The constructor takes an `Engine` (a session is created per call and
committed) **or** an existing `Session` (the caller stays in charge of the
transaction).  Every method of `shared.interfaces.PartsRepository` is
implemented with the frozen signature:

| Method | Behaviour |
| --- | --- |
| `add_part(part)` | Upsert of the part, its values and its offers. A value without a `param_id` is matched on `(part_id, name, unit)`, so calling it twice does not duplicate anything. Returns the stored record. |
| `get_part(part_id)` | The part with **all** values (any status), its offers and its source ids. |
| `get_part_by_mpn(mpn)` | The first part with that manufacturer part number. |
| `list_parts(filt, limit, offset)` | `(summaries, total)`. `total` is the number of matches **before** `limit`/`offset`. |
| `get_parameters(part_id)` | Every stored value of a part. |
| `get_parameter(param_id)` | One value, `None` when it does not exist. |
| `update_parameter(value)` | Persists a changed value. `ValueError` without a `param_id`, `KeyError` when the row does not exist. |
| `add_source(source)` | Upsert of a source record. |
| `get_source(source_id)` | One source, `None` when it does not exist. |
| `get_source_page(source_id, page)` | One page of a source (see below). |
| `add_offer(part_id, offer)` | Upsert of one offer (matched on `offer_id` or on `part_id` + `distributor` + `sku`). |
| `list_review_queue(limit, offset)` | The values with `status='review'`, **least confident first**. |
| `apply_review(param_id, decision)` | `accept` -> `accepted`/`manual`/1.0, `correct` -> the corrected values + `accepted`/`manual`/1.0, `reject` -> `rejected`. Every decision is written to `review_corrections`. Returns a `ReviewResponse` with the updated `ReviewItem`. `KeyError` for an unknown id. |
| `record_llm_call(record)` | One row of `llm_calls`. |
| `stats()` | The dashboard numbers (see below). |

Extras (not part of the protocol, safe to ignore):

* `add_source_page(source_id, page, text, *, width, height, image_url, is_image_only)`
  caches the text of one page in the `sources.note` field.
* `NameMapRepository`: `lookup(raw_name, family)`, `add(raw_name, standard_name, family, approved)`,
  `all_mappings(family)`, `set_approved(raw_name, approved)`, `remove(raw_name, family)`.

### How `list_parts` executes a `SearchFilter`

| Filter | SQL |
| --- | --- |
| `family` | `parts.family = ...` |
| `manufacturer` | case-insensitive equality |
| `manufacturer_in` | `IN (...)` |
| `mpn_contains` | case-insensitive `LIKE '%...%'` (`%` and `_` of the input are escaped) |
| `package` / `package_in` | equality / `IN (...)` |
| `lifecycle_status` | `IN (...)` |
| `in_stock` | `EXISTS (SELECT 1 FROM offers WHERE part_id = ... AND stock > 0)` (`False` negates it) |
| `text` | case-insensitive `LIKE` over `mpn`, `description` and `manufacturer` |
| `parameters` | one `EXISTS` sub-query per constraint on `parameters` |

A parameter constraint is executed as
`EXISTS (SELECT 1 FROM parameters WHERE part_id = parts.part_id AND name = :name AND status IN ('accepted','review') AND value IS NOT NULL AND <value comparison>)`.

* The comparison happens in the **canonical unit**: the constraint is converted
  with `db.units.canonicalize()` (`5 mohm` -> `0.005 ohm`) and the stored value
  is scaled into the canonical unit by a SQL `CASE` expression, so a value
  that was stored as `12 mohm` matches a constraint of `5 mohm` *and* one of
  `0.005 ohm`.
* A constraint without a unit uses the canonical unit of the standard name
  (`db.units.PARAMETER_UNITS`, e.g. `rds_on` -> `ohm`).
* The operators follow `ParameterConstraint.bounds()`: `lt` `<`, `lte` `<=`,
  `gt` `>`, `gte` `>=`, `eq` `==`, `between` `>= and <=`.
* A value with the status `rejected` never satisfies a constraint.

### `stats()`

* `parts_total`, `parts_by_family`, `parts_by_lifecycle`, `parts_by_manufacturer`
* `parameters_total`, `values_by_status`, `values_by_method`, `review_pending`
* `sources_total`
* `coverage_pct` - **share of parts that have at least one accepted value**
  (0 - 100).  A part without any accepted value counts as not covered.
* `mean_confidence` - the average confidence of all stored values.
* `llm_calls_total`, `llm_tokens_in`, `llm_tokens_out`, `llm_cost_total`
* `avg_cost_per_datasheet` - `llm_cost_total / number of distinct PDF sources`
  (0 when there is no PDF source).

---

## 3. How to run it

```bash
cd backend
.venv/bin/python -m pytest -q          # the whole backend suite
.venv/bin/python -m pytest tests/db -q # only the data layer
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .
```

### Seed the database

```bash
cd backend
.venv/bin/python -m db.seed                      # into Settings.database_url
.venv/bin/python -m db.seed --database-url sqlite:///tmp/x.db
.venv/bin/python -m db.seed --path other.json --name-map other_map.json
```

`make seed` (from the repository root) runs the same command.  The loader is
**idempotent**: the second run does not change a single row.  It writes

* 30 parts (`contracts/fixtures/seed/parts.json`),
* 390 values (13 per part) with `method=api`, `confidence=0.9`,
  `status=accepted` (a value without a number becomes `status=review`),
  a synthetic `source_id` (`api-digikey-<mpn lower>`) and the **canonical**
  unit (`mohm` -> `ohm`, `nC` -> `C`, `pF` -> `F`, `ns` -> `s`),
* 60 synthetic sources (two per part, `https://example.invalid/...`),
* 44 name map entries.

---

## 4. Schema and migrations

`init_db(engine)` does three things, in this order:

1. `apply_reference_schema(engine)` executes the **frozen**
   `backend/shared/db_schema.sql`.  The file uses `CREATE TABLE IF NOT EXISTS`
   everywhere, so the tables carry the exact CHECK constraints and indexes of
   the contract.
2. `migrate(engine)` applies the numbered SQL files of
   `backend/db/migrations/` that were never applied and records them in the
   `schema_migrations` table (version + sha256 of the file).
3. `Base.metadata.create_all(checkfirst=True)` is the safety net for a table
   that only exists in the ORM.  It never touches an existing table, so it can
   never remove a CHECK constraint.

### Why plain SQL migrations instead of alembic

The schema of the project is **one frozen DDL file** that the orchestrator
owns.  Plain, ordered SQL files keep the history readable, have no Python
import path dependencies and cannot drift away from the reference schema.
The rule is the usual one: **never edit an applied migration, add a new
numbered file**.

`backend/tests/db/test_schema.py` compares the created database with the
reference schema (tables, columns, indexes) so the two can never diverge.

---

## 5. Assumptions about the frozen contracts

* **Timestamps.**  The reference schema stores them as TEXT with
  `datetime('now')` as the server default.  The ORM writes ISO-8601 with an
  explicit UTC offset (`2026-01-01T12:00:00.000000+00:00`) so that a round
  trip returns the same aware `datetime` that went in.  `parse_timestamp()`
  reads both formats.
* **JSON columns.**  `parts.source_ids`, `parameters.condition` and
  `offers.price_breaks` are `sqlalchemy.JSON`; SQLite stores them as TEXT,
  which is what the reference schema does.
* **Enum-like columns** are plain `String` with the values of the CHECK
  constraints (`family`, `lifecycle_status`, `type`, `method`, `status`,
  `approved`, `action`).
* **Foreign keys are enforced** (`PRAGMA foreign_keys=ON` on every SQLite
  connection).  A value that references a source has to be registered with
  `add_source()` **before** the part is stored - `add_part()` raises a
  `ValueError` with a clear message instead of an `IntegrityError`.
* **`sources.note`** carries the page cache: a JSON document
  `{"note": "<the original free text>", "pages": {"1": {"text": "..."}}}`
  (see `add_source_page`).  `get_source_page` falls back to the local PDF
  (`sources.local_path`, PyMuPDF) and finally returns a page without text.
  `None` is only returned when the source itself does not exist.
* **Status of a value in a search.**  A constraint is satisfied by `accepted`
  and `review` values, never by a `rejected` one.  The summary columns
  (`key_parameters`) only use `accepted` values.
* **`key_parameters`** - MOSFET: `vds_max`, `id_continuous`, `rds_on`,
  `total_gate_charge_qg`; gate driver: `supply_voltage_min`,
  `supply_voltage_max`, `peak_source_current`, `propagation_delay`.  A missing
  value is `None`.
* **`total_stock`** is the sum of the stock of all offers of a part (`0` when
  the part has no offer).
* **The canonical unit policy is duplicated** in `db/units.py`.  No agent may
  import the package of another agent, so the validator's unit module cannot
  be reused.  The duplication is deliberate and small.

---

## 6. Known gaps

* **No pagination helper for the review queue beyond `limit`/`offset`** - the
  queue itself is a plain query.
* **`reasons` of a `ReviewItem`** are derived by the repository (low
  confidence, missing source).  A richer reason list would have to come from
  the validator, which does not store reasons in the frozen schema.
* **The name map has no fuzzy matching.**  `lookup()` is an exact match on the
  raw name; the tier-1 agent is expected to normalise the header before it
  looks it up (the alias table of the seed covers the common spellings).
* **`channel_count`, `package` and `input_logic_level`** are not in the
  `db.units.PARAMETER_UNITS` registry (they are not numeric or unitless).
* **The migrations do not run against a live production database yet** - the
  project is new, the first migration creates everything.
* No change request was needed: the data layer only needed the frozen
  contract layer, and `db/seed_data/name_map.json` lives inside the folder of
  this agent.

---

## 7. Integration notes for the other agents

* **B (tier 1)** can use `NameMapRepository.lookup(raw_name, family)` to map a
  table header to a standard name, and `add(...)` to propose a new one.
* **C (LLM)** can use `NameMapRepository.add(..., approved=False)` for a
  proposal and `record_llm_call()` for the cost accounting.
* **D (validation)** returns `ParameterValue` objects; `update_parameter()`
  persists them.  The canonical unit of a value is expected to be the pint
  unit of the contract (`V`, `A`, `ohm`, `degC`, ...).
* **F (services)** can build the `SearchFilter` and hand it to
  `list_parts()`; the LLM never chooses the results, the database executes
  the filter.
* **G (API)** can use `init_db()` on start-up, `SqlAlchemyPartsRepository` for
  the routes and `stats()` for `/api/stats`.
