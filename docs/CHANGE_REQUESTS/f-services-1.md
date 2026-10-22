# Change request F-1: stock data and canonical units in the seed fixture

**From:** agent F (services)
**Files affected (not owned by me):**
`contracts/fixtures/seed/parts.json`, `contracts/fixtures/seed/seed_parts.csv`

## What I need

1. **Offer / stock data.** The seed fixture only holds
   `part_id, mpn, manufacturer, family, package, lifecycle_status,
   datasheet_url, description, source_ids, parameters`. There is no
   distributor offer and no stock number.

   The BOM health check (FR-14) needs the stock and the number of
   distributors to raise `low_stock` and `single_source`, and the
   alternatives ranking adds a stock bonus. With the current fixture
   neither can be verified against the seed data.

   *Proposal:* add an `offers` list per part, e.g.

   ```json
   "offers": [
     {"distributor": "digikey", "stock": 4210, "unit_price": 1.23, "currency": "USD"},
     {"distributor": "mouser", "stock": 1180, "unit_price": 1.31, "currency": "USD"}
   ]
   ```

   The values do not have to be real - they have to be plausible and
   deterministic. The same information would be useful in
   `seed_parts.csv` (columns `stock`, `distributor`).

2. **Canonical units.** The frozen contract says "Units are always SI base
   units", but the seed stores `rds_on` in `mohm` (and `total_gate_charge_qg`
   in `nC`, `propagation_delay` in `ns`). The services compare two raw
   numbers (a relative difference), so every part of a family must use the
   same unit for the same parameter.

   *Proposal:* pick one convention and use it everywhere -
   either the SI base unit (`ohm`, `C`, `s`) or the datasheet unit (`mohm`,
   `nC`, `ns`) - and state it in `docs/CONTRACTS.md`. My recommendation:
   keep the datasheet unit in the database (that is what the datasheets and
   the frontend show) and normalise only in the API layer.

## Why it matters

* `services/alternatives.py` computes `|candidate - reference| / |reference|`.
  Mixed units would produce a wrong distance and a wrong ranking.
* `services/bom.py` cannot raise `low_stock` / `single_source` without stock
  and distributor data.

## Workaround while the request is open

`backend/tests/services/fakes.py` synthesises deterministic offers for the
seed parts (`fakes.synthesize_offers`) and the BOM tests use explicit parts
with explicit offers. Nothing blocks the services; the numbers are simply
not verifiable against the seed fixture yet.
