-- Covering index for "latest price per symbol <= date": ordered probe + index-only scan.
CREATE INDEX IF NOT EXISTS ix_price_symbol_date_rank
    ON core.commodity_price (symbol, price_date DESC, source_rank) INCLUDE (price);

CREATE INDEX IF NOT EXISTS ix_position_symbol      ON core.position (symbol);
CREATE INDEX IF NOT EXISTS ix_stg_price_batch      ON staging.stg_price (batch_id);
CREATE INDEX IF NOT EXISTS ix_stg_position_batch   ON staging.stg_position (batch_id);

-- Defect work-queue: only open items are indexed.
CREATE INDEX IF NOT EXISTS ix_failed_open
    ON etl.failed_record (error_code, last_seen_at DESC) WHERE NOT resolved;
