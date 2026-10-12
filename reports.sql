-- name: default_report_date
SELECT max(price_date) AS report_date FROM core.commodity_price;

-- name: exposure_detail
SELECT book, symbol, commodity, unit, quantity, avg_cost, price_date, mkt_price, prev_price,
       exposure, unrealized_pnl, daily_pnl, is_stale
FROM core.fn_exposure_pnl(%(report_date)s);

-- name: exposure_by_commodity
SELECT COALESCE(symbol, 'TOTAL') AS symbol,
       count(*)                  AS positions,
       sum(quantity)             AS net_quantity,
       sum(exposure)             AS net_exposure,
       sum(abs(exposure))        AS gross_exposure,
       sum(daily_pnl)            AS daily_pnl,
       sum(unrealized_pnl)       AS unrealized_pnl
FROM core.fn_exposure_pnl(%(report_date)s)
GROUP BY ROLLUP (symbol)
ORDER BY GROUPING(symbol), symbol;

-- name: exposure_by_book
SELECT COALESCE(book, 'TOTAL')   AS book,
       count(*)                  AS positions,
       sum(exposure)             AS net_exposure,
       sum(abs(exposure))        AS gross_exposure,
       sum(daily_pnl)            AS daily_pnl,
       sum(unrealized_pnl)       AS unrealized_pnl
FROM core.fn_exposure_pnl(%(report_date)s)
GROUP BY ROLLUP (book)
ORDER BY GROUPING(book), book;

-- name: open_defects_summary
SELECT f.target, f.source, f.error_code, count(*) AS records, sum(f.occurrences) AS occurrences,
       max(f.last_seen_at) AS last_seen_at
FROM etl.failed_record f
WHERE NOT f.resolved
GROUP BY f.target, f.source, f.error_code
ORDER BY f.target, f.source, f.error_code;

-- name: open_defects_detail
SELECT f.failed_id, f.target, f.source, f.error_code, f.error_message, ec.suggested_resolution,
       f.raw_payload::text AS raw_payload, f.occurrences, f.first_seen_at, f.last_seen_at, f.batch_id
FROM etl.failed_record f
JOIN etl.error_code ec USING (error_code)
WHERE NOT f.resolved
ORDER BY f.target, f.error_code, f.failed_id;
