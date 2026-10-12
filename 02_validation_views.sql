-- Single source of truth for validation rules.
-- error_code IS NULL  -> row is clean and will be upserted
-- error_code NOT NULL -> row goes to etl.failed_record
-- Window partitions include batch_id so batch filters push down into the view.

CREATE OR REPLACE VIEW staging.v_price_checked AS
WITH parsed AS (
    SELECT s.stg_id, s.batch_id, s.source,
           upper(NULLIF(btrim(s.symbol), ''))   AS symbol,
           etl.try_date(s.price_date)           AS price_date,
           etl.try_numeric(s.price)             AS price,
           upper(NULLIF(btrim(s.currency), '')) AS currency,
           s.raw_payload
    FROM staging.stg_price s
), base AS (
    SELECT p.stg_id, p.batch_id, p.source, p.symbol, p.price_date, p.price, p.raw_payload,
           COALESCE(p.currency, c.currency) AS currency,
           CASE
               WHEN p.symbol IS NULL                                  THEN 'MISSING_SYMBOL'
               WHEN c.symbol IS NULL                                  THEN 'UNKNOWN_SYMBOL'
               WHEN p.price_date IS NULL                              THEN 'BAD_DATE'
               WHEN p.price_date > CURRENT_DATE                       THEN 'FUTURE_DATE'
               WHEN p.price IS NULL                                   THEN 'BAD_PRICE'
               WHEN p.price <= 0                                      THEN 'NON_POSITIVE_PRICE'
               WHEN p.price >= 1000000000                             THEN 'PRICE_OUT_OF_RANGE'
               WHEN COALESCE(p.currency, c.currency) <> c.currency    THEN 'CURRENCY_MISMATCH'
           END AS base_error
    FROM parsed p
    LEFT JOIN ref.commodity c ON c.symbol = p.symbol
), ranked AS (
    SELECT b.*,
           row_number() OVER (
               PARTITION BY b.batch_id, b.source, b.symbol, b.price_date, (b.base_error IS NULL)
               ORDER BY b.stg_id DESC          -- last record in the feed wins
           ) AS rn
    FROM base b
)
SELECT stg_id, batch_id, source, symbol, price_date, price, currency, raw_payload,
       COALESCE(base_error, CASE WHEN rn > 1 THEN 'DUPLICATE_IN_BATCH' END) AS error_code
FROM ranked;

CREATE OR REPLACE VIEW staging.v_position_checked AS
WITH parsed AS (
    SELECT s.stg_id, s.batch_id, s.source,
           NULLIF(btrim(s.position_id), '')       AS position_id,
           NULLIF(btrim(s.book), '')              AS book,
           upper(NULLIF(btrim(s.symbol), ''))     AS symbol,
           etl.try_numeric(s.quantity)            AS quantity,
           etl.try_numeric(s.avg_cost)            AS avg_cost,
           s.raw_payload
    FROM staging.stg_position s
), base AS (
    SELECT p.*,
           CASE
               WHEN p.position_id IS NULL                                    THEN 'MISSING_POSITION_ID'
               WHEN p.book IS NULL                                           THEN 'MISSING_BOOK'
               WHEN p.symbol IS NULL                                         THEN 'MISSING_SYMBOL'
               WHEN c.symbol IS NULL                                         THEN 'UNKNOWN_SYMBOL'
               WHEN p.quantity IS NULL OR abs(p.quantity) >= 1000000000000   THEN 'BAD_QUANTITY'
               WHEN p.avg_cost IS NULL OR p.avg_cost <= 0
                    OR p.avg_cost >= 1000000000                              THEN 'BAD_AVG_COST'
           END AS base_error
    FROM parsed p
    LEFT JOIN ref.commodity c ON c.symbol = p.symbol
), ranked AS (
    SELECT b.*,
           row_number() OVER (
               PARTITION BY b.batch_id, b.position_id, (b.base_error IS NULL)
               ORDER BY b.stg_id DESC
           ) AS rn
    FROM base b
)
SELECT stg_id, batch_id, source, position_id, book, symbol, quantity, avg_cost, raw_payload,
       COALESCE(base_error, CASE WHEN rn > 1 THEN 'DUPLICATE_IN_BATCH' END) AS error_code
FROM ranked;
