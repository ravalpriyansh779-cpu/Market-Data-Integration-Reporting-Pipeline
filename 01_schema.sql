-- Schemas ------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS ref;      -- reference data
CREATE SCHEMA IF NOT EXISTS staging;  -- raw, untyped landing tables (everything TEXT)
CREATE SCHEMA IF NOT EXISTS core;     -- validated, typed, constrained data
CREATE SCHEMA IF NOT EXISTS etl;      -- batch control + failed-record log

-- Reference ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref.commodity (
    symbol   TEXT PRIMARY KEY,
    name     TEXT    NOT NULL,
    unit     TEXT    NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD'
);

-- ETL control ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl.batch_log (
    batch_id      BIGSERIAL PRIMARY KEY,
    source        TEXT NOT NULL CHECK (source IN ('API', 'CSV')),
    target        TEXT NOT NULL CHECK (target IN ('PRICE', 'POSITION')),
    status        TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    rows_staged   INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    rows_updated  INTEGER NOT NULL DEFAULT 0,
    rows_failed   INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS etl.error_code (
    error_code           TEXT PRIMARY KEY,
    description          TEXT NOT NULL,
    suggested_resolution TEXT NOT NULL
);

-- Staging: raw strings exactly as received; no constraints on content --------
CREATE TABLE IF NOT EXISTS staging.stg_price (
    stg_id      BIGSERIAL PRIMARY KEY,
    batch_id    BIGINT NOT NULL REFERENCES etl.batch_log (batch_id),
    source      TEXT   NOT NULL,
    symbol      TEXT,
    price_date  TEXT,
    price       TEXT,
    currency    TEXT,
    raw_payload JSONB  NOT NULL,
    staged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.stg_position (
    stg_id      BIGSERIAL PRIMARY KEY,
    batch_id    BIGINT NOT NULL REFERENCES etl.batch_log (batch_id),
    source      TEXT   NOT NULL,
    position_id TEXT,
    book        TEXT,
    symbol      TEXT,
    quantity    TEXT,
    avg_cost    TEXT,
    raw_payload JSONB  NOT NULL,
    staged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Core ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.commodity_price (
    symbol      TEXT        NOT NULL REFERENCES ref.commodity (symbol),
    price_date  DATE        NOT NULL,
    source      TEXT        NOT NULL CHECK (source IN ('API', 'CSV')),
    price       NUMERIC(18, 6) NOT NULL CHECK (price > 0),
    currency    CHAR(3)     NOT NULL,
    -- API wins over CSV when both carry the same (symbol, date)
    source_rank SMALLINT GENERATED ALWAYS AS (CASE source WHEN 'API' THEN 1 ELSE 2 END) STORED,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, price_date, source)
);

CREATE TABLE IF NOT EXISTS core.position (
    position_id TEXT PRIMARY KEY,
    book        TEXT NOT NULL,
    symbol      TEXT NOT NULL REFERENCES ref.commodity (symbol),
    quantity    NUMERIC(18, 4) NOT NULL,          -- signed: negative = short
    avg_cost    NUMERIC(18, 6) NOT NULL CHECK (avg_cost > 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Failed-record log: one row per distinct defect, re-occurrences are counted --
CREATE TABLE IF NOT EXISTS etl.failed_record (
    failed_id       BIGSERIAL PRIMARY KEY,
    fingerprint     TEXT   NOT NULL UNIQUE,
    batch_id        BIGINT NOT NULL REFERENCES etl.batch_log (batch_id),
    target          TEXT   NOT NULL,
    source          TEXT   NOT NULL,
    stg_id          BIGINT,
    error_code      TEXT   NOT NULL REFERENCES etl.error_code (error_code),
    error_message   TEXT   NOT NULL,
    raw_payload     JSONB  NOT NULL,
    occurrences     INTEGER NOT NULL DEFAULT 1,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    resolution_note TEXT
);

-- Safe parsers used by the validation views (never raise, return NULL) -------
CREATE OR REPLACE FUNCTION etl.try_numeric(p TEXT) RETURNS NUMERIC
LANGUAGE plpgsql STABLE AS $$
DECLARE v NUMERIC;
BEGIN
    IF p IS NULL OR btrim(p) = '' THEN RETURN NULL; END IF;
    v := btrim(p)::NUMERIC;
    IF v::TEXT IN ('NaN', 'Infinity', '-Infinity') THEN RETURN NULL; END IF;
    RETURN v;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION etl.try_date(p TEXT) RETURNS DATE
LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF p IS NULL OR btrim(p) !~ '^\d{4}-\d{2}-\d{2}$' THEN RETURN NULL; END IF;
    RETURN btrim(p)::DATE;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END $$;
