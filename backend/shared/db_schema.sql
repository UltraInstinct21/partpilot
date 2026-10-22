-- PartPilot database schema (CONTRACT v1).
-- Plan section 7. This file is the reference for the SQLAlchemy models in
-- backend/db/models.py (owned by agent E-data).
--
-- Conventions:
--   * All primary keys are TEXT (UUID4 hex or a stable natural key).
--   * `parameters` stores one row per extracted value. The row keeps the full
--     provenance required by FR-05 and FR-09: source_id, page, method, tier,
--     confidence, status and the test condition (JSON).
--   * `parameters.value` is the canonical single value. `value_min`,
--     `value_typ` and `value_max` keep the min/typ/max triple when the source
--     table has it.
--   * `parameters.unit` is the canonical pint unit (V, A, ohm, degC, F, s, ...).

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- parts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parts (
    part_id            TEXT PRIMARY KEY,
    mpn                TEXT NOT NULL,
    manufacturer       TEXT NOT NULL,
    family             TEXT NOT NULL CHECK (family IN ('mosfet', 'gate_driver')),
    package            TEXT,
    lifecycle_status   TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (lifecycle_status IN ('active', 'nrnd', 'obsolete', 'unknown')),
    datasheet_url      TEXT,
    description        TEXT,
    source_ids         TEXT NOT NULL DEFAULT '[]',  -- JSON array of source_id
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (mpn, manufacturer)
);

CREATE INDEX IF NOT EXISTS idx_parts_family ON parts (family);
CREATE INDEX IF NOT EXISTS idx_parts_manufacturer ON parts (manufacturer);
CREATE INDEX IF NOT EXISTS idx_parts_package ON parts (package);
CREATE INDEX IF NOT EXISTS idx_parts_lifecycle ON parts (lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_parts_mpn ON parts (mpn);

-- ---------------------------------------------------------------------------
-- sources  (provenance for every downloaded or fetched artefact)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id      TEXT PRIMARY KEY,
    url            TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN ('api', 'pdf', 'manual')),
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now')),
    file_hash      TEXT,
    distributor    TEXT,
    page_count     INTEGER,
    local_path     TEXT,
    content_type   TEXT,
    note           TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources (file_hash);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources (type);

-- ---------------------------------------------------------------------------
-- parameters  (one extracted value with its provenance)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parameters (
    param_id     TEXT PRIMARY KEY,
    part_id      TEXT NOT NULL REFERENCES parts (part_id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    value        REAL,
    value_min    REAL,
    value_typ    REAL,
    value_max    REAL,
    unit         TEXT,
    condition    TEXT NOT NULL DEFAULT '{}',   -- JSON object: {"vgs": "10 V", "temp": "25 C"}
    source_id    TEXT REFERENCES sources (source_id) ON DELETE SET NULL,
    page         INTEGER,
    method       TEXT CHECK (method IN ('tier1', 'tier2', 'tier3', 'api', 'manual')),
    confidence   REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    status       TEXT NOT NULL DEFAULT 'review'
                 CHECK (status IN ('accepted', 'review', 'rejected')),
    raw_text     TEXT,
    value_text   TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_parameters_part ON parameters (part_id);
CREATE INDEX IF NOT EXISTS idx_parameters_name ON parameters (name);
CREATE INDEX IF NOT EXISTS idx_parameters_status ON parameters (status);
CREATE INDEX IF NOT EXISTS idx_parameters_method ON parameters (method);
CREATE INDEX IF NOT EXISTS idx_parameters_source ON parameters (source_id);

-- ---------------------------------------------------------------------------
-- offers  (distributor price and stock)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offers (
    offer_id       TEXT PRIMARY KEY,
    part_id        TEXT NOT NULL REFERENCES parts (part_id) ON DELETE CASCADE,
    distributor    TEXT NOT NULL,
    sku            TEXT,
    stock          INTEGER,
    unit_price     REAL,
    currency       TEXT NOT NULL DEFAULT 'USD',
    price_breaks   TEXT NOT NULL DEFAULT '[]',  -- JSON array of {quantity, price}
    lead_time_days INTEGER,
    url            TEXT,
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_offers_part ON offers (part_id);
CREATE INDEX IF NOT EXISTS idx_offers_distributor ON offers (distributor);

-- ---------------------------------------------------------------------------
-- name_map  (raw parameter name -> standard name)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS name_map (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_name       TEXT NOT NULL,
    standard_name  TEXT NOT NULL,
    family         TEXT CHECK (family IN ('mosfet', 'gate_driver')),
    approved       TEXT NOT NULL DEFAULT 'no' CHECK (approved IN ('yes', 'no')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (raw_name, family)
);

CREATE INDEX IF NOT EXISTS idx_name_map_raw ON name_map (raw_name);
CREATE INDEX IF NOT EXISTS idx_name_map_standard ON name_map (standard_name);

-- ---------------------------------------------------------------------------
-- llm_calls  (cost and token accounting, NFR-05)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id        TEXT PRIMARY KEY,
    chain          TEXT NOT NULL,
    model          TEXT NOT NULL,
    tokens_in      INTEGER NOT NULL DEFAULT 0,
    tokens_out     INTEGER NOT NULL DEFAULT 0,
    cost           REAL NOT NULL DEFAULT 0.0,
    prompt_version TEXT NOT NULL DEFAULT '',
    part_id        TEXT,
    cached         INTEGER NOT NULL DEFAULT 0,
    duration_ms    INTEGER,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_chain ON llm_calls (chain);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls (created_at);

-- ---------------------------------------------------------------------------
-- review_corrections  (human corrections feed back into name_map and prompts)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_corrections (
    correction_id TEXT PRIMARY KEY,
    param_id      TEXT NOT NULL,
    part_id       TEXT,
    action        TEXT NOT NULL CHECK (action IN ('accept', 'correct', 'reject')),
    old_value     REAL,
    new_value     REAL,
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_review_corrections_param ON review_corrections (param_id);
