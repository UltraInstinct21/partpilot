# HANDOFF - validation package (agent D, WP5 / FR-06 / FR-07 / FR-08 / FR-10)

Branch: `agent/d-validation`.  Everything below lives in `backend/validation/`
and `backend/tests/validation/`.

## 1. What exists

| File | Purpose |
| --- | --- |
| `backend/validation/units.py` | `pint` normalisation (FR-06). One `UnitRegistry` (`ureg`), `normalize()`, `canonical_unit_for()`, `PARAMETER_UNITS`, `clean_unit()`, `is_known_unit()`. |
| `backend/validation/rules.py` | The range table (FR-07): `FieldRule`, `FIELD_RULES`, `rule_for()`, `tolerance_for()`, `values_agree()`, `relative_difference()`. |
| `backend/validation/confidence.py` | The confidence formula: `BASE_CONFIDENCE`, `compute_confidence()`, `REVIEW_THRESHOLD`. |
| `backend/validation/namemap.py` | `NameMatcher` (rapidfuzz), `DEFAULT_ALIASES`, `normalize_name()`. |
| `backend/validation/validator.py` | `ParameterValidator` (implements the frozen `Validator` protocol), `ValidationOutcome`, `get_validator()`. |
| `backend/validation/__init__.py` | Public exports of the package. |
| `backend/tests/validation/` | 196 tests, of which **59 are deliberately wrong values** (the acceptance test of WP5). |

Nothing outside `backend/validation/` and `backend/tests/validation/` was
touched.  The frozen files (`shared/schemas.py`, `shared/interfaces.py`,
`pyproject.toml`, `contracts/**`) are unchanged, so **no change request is
needed**.

## 2. Public API

```python
from validation import ParameterValidator, get_validator, normalize, canonical_unit_for
from validation import NameMatcher, FIELD_RULES, rule_for

validator = get_validator()          # shared, default instance
result   = validator.validate(value)             # -> ParameterValue
result   = validator.validate(value, api_value)  # -> ParameterValue
results  = validator.validate_many(values, api_values)          # -> list[ParameterValue]
outcomes = validator.validate_many_with_reasons(values, api_values)
outcome  = validator.validate_with_reasons(value, api_value=None)

outcome.value        # ParameterValue with the canonical unit, confidence and status
outcome.status       # ValueStatus.ACCEPTED / REVIEW / REJECTED
outcome.confidence   # 0.0 .. 1.0
outcome.reasons      # list[str], human readable, empty for a clean accepted value
outcome.api_value    # the API value the value was compared with
outcome.unit         # the canonical unit
```

`ParameterValue` has no `reasons` field and the frozen schema must not change,
so the reasons are returned by `validate_with_reasons()` in a
`ValidationOutcome` (a dataclass in `validation/validator.py`).  The reason
strings are the ones a reviewer needs, e.g.

* `out of range: vds_max value=5000 V not in [1, 2000]`
* `ordering violation: vds_max min > typ (100 > 50)`
* `not an integer: channel_count value=2.5`
* `unit mismatch for id_continuous: expected A, got V`
* `unknown unit 'bananas' for vds_max`
* `missing unit for vds_max (expected V)`
* `api value disagrees: rds_on 0.012 ohm vs api 0.03 (60.0% off, tolerance 5%)`
* `method tier2 needs review`, `low confidence 0.70`, `missing method: the value has no provenance`

`validate_many(values, api_values)` looks the API value up by the standard
name (`api_values["vds_max"]`); the name is matched case-insensitively as a
fallback.  The API value is expected in the **canonical** unit of the field.

`normalize(value, unit)` (module level and on the validator) returns
`(value, canonical_unit)`.  `normalize(value, unit, expected_unit=...)` adds a
keyword-only hint that only resolves the ambiguous spelling `C` (coulomb vs.
degrees Celsius).  An unknown unit returns `(None, None)` and never raises.

## 3. The range table (FR-07)

The bounds are stored in the **canonical** unit of the field; the comment in
`rules.py` repeats them in the unit a human reads.

| field | unit | min | max | tolerance |
| --- | --- | --- | --- | --- |
| `vds_max` | V | 1 | 2000 | 5 % |
| `id_continuous` | A | 0.01 | 1000 | 5 % |
| `rds_on` | ohm | 0.0001 | 100 | 5 % (floor 1e-6) |
| `vgs_threshold` | V | 0.1 | 5 | 5 % |
| `vgs_max` | V | 1 | 50 | 5 % |
| `total_gate_charge_qg` | C | 0.01 nC | 2000 nC | 5 % (floor 1e-12) |
| `gate_drain_charge_qgd` | C | 0.01 nC | 1000 nC | 5 % (floor 1e-12) |
| `input_capacitance_ciss` | F | 1 pF | 100000 pF | 10 % (floor 1e-15) |
| `output_capacitance_coss` | F | 1 pF | 100000 pF | 10 % (floor 1e-15) |
| `max_junction_temp` | degC | 25 | 300 | 5 % |
| `thermal_resistance` | degC/W | 0.01 | 200 | 5 % |
| `reverse_recovery_qrr` | C | 0.1 nC | 100000 nC | 5 % (floor 1e-12) |
| `supply_voltage_min` | V | 0.5 | 100 | 5 % |
| `supply_voltage_max` | V | 1 | 200 | 5 % |
| `peak_source_current` | A | 0.05 | 200 | 5 % |
| `peak_sink_current` | A | 0.05 | 200 | 5 % |
| `input_logic_level` | V | 0 | 10 | 5 % |
| `propagation_delay` | s | 1 ns | 100 us | 5 % (floor 1e-12) |
| `rise_time` | s | 1 ns | 100 us | 5 % (floor 1e-12) |
| `fall_time` | s | 1 ns | 100 us | 5 % (floor 1e-12) |
| `uvlo_threshold` | V | 0.5 | 100 | 5 % |
| `channel_count` | - | 1 | 8 | integer |
| `operating_temp_min` | degC | -100 | 25 | 5 % |
| `operating_temp_max` | degC | 40 | 300 | 5 % |
| `package` | - | - | - | never range checked |

A name **without** a rule is never rejected for its value ("an unknown field
must not disappear").  The unit of the value is still normalised.

## 4. The confidence formula

```
base      = {tier1: 0.85, tier2: 0.75, tier3: 0.70, api: 0.90, manual: 1.00}[method]
checks    = 0.10 * (range check passed)
          + 0.05 * (min <= typ <= max)
          + 0.05 * (unit converted)
api_match = +0.05 when the API value agrees within the tolerance,
            -0.10 when it disagrees
confidence = clamp(base + checks + api_match, 0.0, 1.0)
```

A check only contributes when it was **applicable**:

* the range bonus needs a field that has a range rule and a value whose unit
  is known,
* the ordering bonus needs at least two of `min`/`typ`/`max`,
* the unit bonus needs a unit that actually had to be converted
  (`12 mohm` -> `0.012 ohm` gives the bonus, `56 V` -> `56 V` does not).

A value without a method (`method=None`) has a base of `0.0` - it has no
provenance and always goes to review.

Status:

* `rejected` - outside the range of the field, `min > typ`, `typ > max`,
  `min > max`, a value that is not a whole number, or a unit that does not
  belong to the field (a voltage for a current).
* `review` - confidence `< 0.75`, the API value disagrees beyond the
  tolerance, the unit is unknown or missing, the method is `tier2`/`tier3`, or
  the method is missing.
* `accepted` - everything else.

## 5. How to run

```bash
cd backend
.venv/bin/python -m pytest -q                 # 215 tests (196 of them mine)
.venv/bin/python -m pytest tests/validation -q
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .
```

No network and no LLM is used in any test.  The only external file the tests
read is the recorded fixture `contracts/fixtures/seed/parts.json`.

## 6. Assumptions about the frozen contracts

1. `ParameterValue` has no `reasons` field -> the reasons travel in
   `ValidationOutcome`.  `shared/schemas.py` was **not** modified.
2. `ParameterValue.representative()` (typ > value > max > min) is the number
   that is compared with the API value.
3. The `unit` field of a stored value is the **canonical** unit
   (`V`, `A`, `ohm`, `F`, `C`, `s`, `degC`, `degC/W`), as the docstring of
   `shared/schemas.py` requires.  A charge is therefore stored in coulomb
   (`37.5 nC` -> `3.75e-08 C`).
4. `api_values` are given in the canonical unit of the field.
5. `ValueStatus` and `ExtractionMethod` are imported from
   `shared/schemas.py`; the method values `tier1`/`tier2`/`tier3`/`api`/
   `manual` match the keys of the confidence table.
6. `pint` 0.26 and `rapidfuzz` 3.14 are already in `backend/pyproject.toml`;
   no dependency was added.

## 7. Known gaps and deliberate choices

* **A value whose unit is unknown or missing is not range checked.**  The
  number could be in any unit, so comparing it with the canonical range would
  be a guess (`37.5` for a gate charge means 37.5 C, not 37.5 nC).  Such a
  value goes to `review` with the reason `unknown unit`/`missing unit`.
* **A unit mismatch is a rejection, not a review.**  A voltage for
  `id_continuous` cannot be compared with the current range, so the value is
  rejected with the reason `unit mismatch`.
* **A rejected value keeps the confidence of the formula** (e.g. 0.85 for a
  tier-1 value that is out of range).  The *status* carries the rejection;
  the confidence is not capped, so the contract formula stays exact.
* **The canonical unit of a temperature difference** (`K`) is reported as
  `degC` with the magnitude kept (`10 K` -> `10 degC`), because the contract
  lists `degC` as the canonical temperature unit.  A bare `C` is a coulomb;
  it is read as degrees Celsius only when the field expects a temperature.
* **`package` is not numeric.**  It arrives with `value=None` and
  `value_text="TO-220AB"`; it is always accepted and never crashes the
  validator.
* **The name map is provisional.**  `DEFAULT_ALIASES` in `namemap.py` is a
  hand written alias table.  `NameMatcher(lookup)` accepts the database
  `name_map` (a mapping of alias -> standard name, or a callable); a mapping
  is merged into the default table, `use_defaults=False` replaces it.
  `NameMatcher.add_alias()` is the hook for the human corrections of WP5
  step 7.
* **No repository, no API, no LLM.**  The validator is a pure function of its
  input; the wiring into the API layer and the review queue (FR-10) belongs to
  the service agents.
