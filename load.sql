-- name: log_failed_prices
INSERT INTO etl.failed_record AS f
       (fingerprint, batch_id, target, source, stg_id, error_code, error_message, raw_payload)
SELECT DISTINCT ON (x.fingerprint)
       x.fingerprint, x.batch_id, 'PRICE', x.source, x.stg_id, x.error_code, ec.description, x.raw_payload
FROM (
    SELECT v.*, md5(concat_ws('|', 'PRICE', v.source, v.error_code, v.raw_payload::text)) AS fingerprint
    FROM staging.v_price_checked v
    WHERE v.batch_id = %(batch_id)s AND v.error_code IS NOT NULL
) x
JOIN etl.error_code ec ON ec.error_code = x.error_code
ORDER BY x.fingerprint, x.stg_id
ON CONFLICT (fingerprint) DO UPDATE
   SET occurrences  = f.occurrences + 1,
       last_seen_at = now(),
       batch_id     = EXCLUDED.batch_id,
       resolved     = FALSE,
       resolved_at  = NULL;

-- name: upsert_prices
INSERT INTO core.commodity_price AS t (symbol, price_date, source, price, currency)
SELECT v.symbol, v.price_date, v.source, v.price, v.currency
FROM staging.v_price_checked v
WHERE v.batch_id = %(batch_id)s AND v.error_code IS NULL
ON CONFLICT (symbol, price_date, source) DO UPDATE
   SET price      = EXCLUDED.price,
       currency   = EXCLUDED.currency,
       updated_at = now()
 WHERE t.price IS DISTINCT FROM EXCLUDED.price
    OR t.currency IS DISTINCT FROM EXCLUDED.currency
RETURNING (xmax = 0) AS inserted;

-- name: log_failed_positions
INSERT INTO etl.failed_record AS f
       (fingerprint, batch_id, target, source, stg_id, error_code, error_message, raw_payload)
SELECT DISTINCT ON (x.fingerprint)
       x.fingerprint, x.batch_id, 'POSITION', x.source, x.stg_id, x.error_code, ec.description, x.raw_payload
FROM (
    SELECT v.*, md5(concat_ws('|', 'POSITION', v.source, v.error_code, v.raw_payload::text)) AS fingerprint
    FROM staging.v_position_checked v
    WHERE v.batch_id = %(batch_id)s AND v.error_code IS NOT NULL
) x
JOIN etl.error_code ec ON ec.error_code = x.error_code
ORDER BY x.fingerprint, x.stg_id
ON CONFLICT (fingerprint) DO UPDATE
   SET occurrences  = f.occurrences + 1,
       last_seen_at = now(),
       batch_id     = EXCLUDED.batch_id,
       resolved     = FALSE,
       resolved_at  = NULL;

-- name: upsert_positions
INSERT INTO core.position AS t (position_id, book, symbol, quantity, avg_cost)
SELECT v.position_id, v.book, v.symbol, v.quantity, v.avg_cost
FROM staging.v_position_checked v
WHERE v.batch_id = %(batch_id)s AND v.error_code IS NULL
ON CONFLICT (position_id) DO UPDATE
   SET book = EXCLUDED.book, symbol = EXCLUDED.symbol,
       quantity = EXCLUDED.quantity, avg_cost = EXCLUDED.avg_cost,
       updated_at = now()
 WHERE (t.book, t.symbol, t.quantity, t.avg_cost)
       IS DISTINCT FROM (EXCLUDED.book, EXCLUDED.symbol, EXCLUDED.quantity, EXCLUDED.avg_cost)
RETURNING (xmax = 0) AS inserted;
