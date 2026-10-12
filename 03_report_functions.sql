-- Daily exposure & P&L per position as of p_report_date.
--   exposure       = quantity * latest price (signed; shorts are negative)
--   unrealized_pnl = (latest price - avg_cost) * quantity
--   daily_pnl      = (latest price - previous price) * quantity, only when the
--                    latest price is dated exactly p_report_date (else NULL + is_stale)
--
-- Query shape: one LATERAL lookup per COMMODITY (tens of rows), not per position
-- (thousands), each an ordered index probe on (symbol, price_date DESC, source_rank)
-- that stops after 2 distinct dates. Positions are then joined to that tiny set.
CREATE OR REPLACE FUNCTION core.fn_exposure_pnl(p_report_date DATE)
RETURNS TABLE (
    book           TEXT,
    symbol         TEXT,
    commodity      TEXT,
    unit           TEXT,
    currency       CHAR(3),
    quantity       NUMERIC,
    avg_cost       NUMERIC,
    price_date     DATE,
    mkt_price      NUMERIC,
    prev_price     NUMERIC,
    exposure       NUMERIC,
    unrealized_pnl NUMERIC,
    daily_pnl      NUMERIC,
    is_stale       BOOLEAN
)
LANGUAGE sql STABLE AS $$
    WITH latest AS (
        SELECT c.symbol, c.name, c.unit, c.currency,
               lp.price_date, lp.price, lp.prev_price
        FROM ref.commodity c
        LEFT JOIN LATERAL (
            SELECT d.price_date, d.price,
                   LEAD(d.price) OVER (ORDER BY d.price_date DESC) AS prev_price
            FROM (
                SELECT DISTINCT ON (cp.price_date) cp.price_date, cp.price
                FROM core.commodity_price cp
                WHERE cp.symbol = c.symbol
                  AND cp.price_date <= p_report_date
                ORDER BY cp.price_date DESC, cp.source_rank
                LIMIT 2
            ) d
            ORDER BY d.price_date DESC
            LIMIT 1
        ) lp ON TRUE
    )
    SELECT p.book, p.symbol, l.name, l.unit, l.currency,
           p.quantity, p.avg_cost,
           l.price_date, l.price, l.prev_price,
           ROUND(p.quantity * l.price, 2),
           ROUND((l.price - p.avg_cost) * p.quantity, 2),
           CASE WHEN l.price_date = p_report_date
                THEN ROUND((l.price - l.prev_price) * p.quantity, 2) END,
           (l.price_date IS DISTINCT FROM p_report_date)
    FROM core.position p
    JOIN latest l ON l.symbol = p.symbol
    ORDER BY p.book, p.symbol, p.position_id
$$;
