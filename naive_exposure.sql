-- BEFORE: typical first-draft report query (correlated subqueries, repeated per position row).
SELECT p.book, p.symbol, p.quantity, p.avg_cost,
       (SELECT cp.price FROM core.commodity_price cp
         WHERE cp.symbol = p.symbol
           AND cp.price_date = (SELECT max(x.price_date) FROM core.commodity_price x
                                 WHERE x.symbol = p.symbol AND x.price_date <= %(report_date)s)
         ORDER BY cp.source_rank LIMIT 1) AS mkt_price,
       (SELECT cp.price FROM core.commodity_price cp
         WHERE cp.symbol = p.symbol
           AND cp.price_date = (SELECT max(x.price_date) FROM core.commodity_price x
                                 WHERE x.symbol = p.symbol
                                   AND x.price_date < (SELECT max(y.price_date) FROM core.commodity_price y
                                                        WHERE y.symbol = p.symbol AND y.price_date <= %(report_date)s))
         ORDER BY cp.source_rank LIMIT 1) AS prev_price
FROM core.position p
JOIN ref.commodity c ON c.symbol = p.symbol
ORDER BY p.book, p.symbol, p.position_id;
