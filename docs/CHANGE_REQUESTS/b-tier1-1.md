# Change request b-tier1-1

**From:** agent b-tier1 (tier-1 extraction)
**To:** orchestrator (owner of `contracts/` and `backend/shared/`)
**Subject:** two conflicts between the tier-1 brief and the frozen fixtures

## 1. Unit canonicalisation: `mohm -> ohm (x 0.001)` vs. the frozen fixture

The brief asks for the normalisation `mohm -> ohm (x 0.001)` (and the same
style for `mV -> V`, `pF -> F`, `ns -> s`, ...), i.e. base units.

The frozen fixture `contracts/fixtures/pdfs/expected_values.json` pins the
**opposite** for exactly the units it exercises:

| field | expected `unit` | expected `value` |
| --- | --- | --- |
| `rds_on` | `mohm` | `5.5` |
| `total_gate_charge_qg` | `nC` | `62` |
| `gate_drain_charge_qgd` | `nC` | `12` |
| `input_capacitance_ciss` | `pF` | `4900` |
| `output_capacitance_coss` | `pF` | `900` |
| `propagation_delay` | `ns` | `20` |

The list of canonical units in the brief (`V`, `A`, `mohm`, `nC`, `pF`,
`degC`, `degC/W`, `ns`) matches the fixture, so the fixture wins: **tier 1
stores the unit exactly as it is printed (canonicalised in spelling only) and
does not rescale the value.**

What tier 1 does today (`backend/extraction/tier1/parsing.py`):

* `mOhm` / `mΩ` -> `mohm`, scale `1.0` (value kept: `5.5` stays `5.5` mohm)
* `nC` -> `nC`, `pF` -> `pF`, `ns` -> `ns` (scale `1.0`)
* `V`, `A`, `degC`, `degC/W` -> unchanged
* every other spelling follows the written table of the brief:
  `mV -> V` (x 0.001), `mA -> A` (x 0.001), `uC -> C` (x 1e-6),
  `nF -> F` (x 1e-9), `us -> s` (x 1e-6), `kOhm -> ohm` (x 1000),
  `uOhm -> ohm` (x 1e-6)

**Request to the validator (agent D) / orchestrator:** the unit strings that
tier 1 emits (`mohm`, `nC`, `pF`, `ns`, `V`, `A`, `degC`, `degC/W`, `ohm`,
`F`, `s`, `C`, `kohm`, ...) are all valid pint units - please normalise them
to the base unit (`mohm -> ohm` = x 0.001, `nC -> C`, `pF -> F`, `ns -> s`)
during validation, exactly as the confidence model of `docs/CONTRACTS.md`
("unit converted" bonus check) describes. No change to the frozen fixture is
needed; only the validator has to know that the value and the unit travel
together.

If the intent is the other way round (tier 1 rescales to base units), the
fixture has to change - it is frozen, so please decide and tell us.

## 2. `channel_count` for the synthetic gate driver

`contracts/fixtures/pdfs/expected_values.json` expects
`channel_count = 1` (`unit: null`, `page: 1`) for
`pdfs/synthetic_gate_driver.pdf`, but that PDF contains **no channel count
cell** - the only hint is the pair of output current rows `Peak Source
Current (IO+)` / `Peak Sink Current (IO-)`.

Tier 1 therefore derives the channel count **structurally** from the output
current symbols (`IO+`/`IO-` = one channel, `IO1+`/`IO2+` = two channels) and
stores it with

* `confidence = 0.5` (much lower than the 0.85 of a read value),
* `status = REVIEW`,
* a note in `ExtractionResult.notes` that says the value was *derived*,
  not read.

This is the only value in the whole tier-1 output that is not read from a
cell. It is marked as such everywhere, but it is still an inference.

**Request:** please confirm that a clearly marked structural inference
(confidence 0.5 + note) is acceptable for tier 1, or drop `channel_count`
from the fixture / move it to a manual value. We did not want to leave the
field empty, because the frozen fixture says it has to be there.

## 3. Minor: `value` vs. `value_typ` / `value_max`

The fixture records `value_max` for `input_logic_level` (a max-only row) but
not for `vgs_max` (also a max-only row). Tier 1 always fills
`value_min` / `value_typ` / `value_max` from the matching column, so
`vgs_max` gets `value = 20`, `value_max = 20`, `value_typ = None`. The tier-1
tests therefore assert only the keys that the fixture actually records
(subset semantics) - if the graders prefer strict equality of the four
fields, please say so and we will align.
