"""Measure the report query before/after optimisation on synthetic data (scratch DB: marketdata_bench).

BEFORE: sql/benchmark/naive_exposure.sql (correlated subqueries) with only the primary-key index.
AFTER : core.fn_exposure_pnl() (per-commodity LATERAL probes) + covering index from 04_indexes.sql.

    python scripts/benchmark.py --symbols 100 --days 5000 --positions 20000
"""
import argparse
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from psycopg2.extensions import make_dsn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marketdata import config  # noqa: E402
from marketdata.db import SQL_DIR, connect, ensure_database, init_schema  # noqa: E402


def timed(cur, sql, params, runs):
    times, rows = [], None
    for _ in range(runs):
        t = time.perf_counter()
        cur.execute(sql, params)
        rows = cur.fetchall()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=100)
    ap.add_argument("--days", type=int, default=5000)
    ap.add_argument("--positions", type=int, default=20000)
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()

    dsn = make_dsn(config.DATABASE_URL, dbname="marketdata_bench")
    ensure_database(dsn)
    conn = connect(dsn)
    init_schema(conn)
    cur = conn.cursor()
    cur.execute("TRUNCATE core.commodity_price, core.position, ref.commodity CASCADE")
    cur.execute("INSERT INTO ref.commodity SELECT 'S' || lpad(i::text, 4, '0'), 'Synthetic ' || i, 'unit', 'USD' "
                "FROM generate_series(1, %s) i", (a.symbols,))
    cur.execute("""INSERT INTO core.commodity_price (symbol, price_date, source, price, currency)
                   SELECT c.symbol, d::date, CASE WHEN random() < 0.2 THEN 'API' ELSE 'CSV' END,
                          10 + random() * 90, 'USD'
                   FROM ref.commodity c, generate_series(current_date - %s, current_date, interval '1 day') d
                   WHERE extract(isodow FROM d) < 6
                   ON CONFLICT DO NOTHING""", (a.days,))
    cur.execute("""INSERT INTO core.position (position_id, book, symbol, quantity, avg_cost)
                   SELECT 'P' || i, 'BOOK' || (i %% 20), 'S' || lpad((1 + i %% %s)::text, 4, '0'),
                          (random() - 0.5) * 2000, 10 + random() * 90
                   FROM generate_series(1, %s) i""", (a.symbols, a.positions))
    conn.commit()
    cur.execute("ANALYZE")
    cur.execute("SELECT count(*) FROM core.commodity_price")
    n_prices = cur.fetchone()[0]
    d = date.today()

    cur.execute("DROP INDEX IF EXISTS core.ix_price_symbol_date_rank")
    conn.commit()
    naive = (SQL_DIR / "benchmark" / "naive_exposure.sql").read_text()
    before_ms, before = timed(cur, naive, {"report_date": d}, a.runs)

    init_schema(conn)  # recreates the covering index
    cur.execute("ANALYZE core.commodity_price")
    conn.commit()
    after_ms, after = timed(cur, "SELECT book, symbol, quantity, avg_cost, mkt_price, prev_price "
                                 "FROM core.fn_exposure_pnl(%(report_date)s)", {"report_date": d}, a.runs)

    key = lambda r: (r[0], r[1], r[2])
    b = sorted(((r[0], r[1], float(r[2]), float(r[4]) if r[4] is not None else None) for r in before))
    f = sorted(((r[0], r[1], float(r[2]), float(r[4]) if r[4] is not None else None) for r in after))
    same_rows = len(b) == len(f)
    # same prices? compare totals of quantity * price (random source choice is identical in both)
    tb = sum(q * p for _, _, q, p in b if p is not None)
    tf = sum(q * p for _, _, q, p in f if p is not None)
    print(f"price rows: {n_prices:,}   positions: {a.positions:,}   symbols: {a.symbols}")
    print(f"BEFORE (correlated subqueries, PK index only) : {before_ms:9.1f} ms (median of {a.runs})")
    print(f"AFTER  (LATERAL per commodity + covering idx) : {after_ms:9.1f} ms (median of {a.runs})")
    print(f"speed-up: {before_ms / after_ms:.1f}x   rows equal: {same_rows}   "
          f"exposure totals match: {abs(tb - tf) < 1e-6 * max(1, abs(tb))}")


if __name__ == "__main__":
    main()
