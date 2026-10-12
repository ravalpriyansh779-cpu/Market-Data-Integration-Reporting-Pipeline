"""Stage -> validate (SQL) -> log failures -> upsert, one auditable batch at a time."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from psycopg2.extras import Json, execute_values

from .db import load_queries

log = logging.getLogger(__name__)
Q = load_queries("queries/load.sql")


@dataclass
class BatchResult:
    batch_id: int
    source: str
    target: str
    staged: int
    inserted: int
    updated: int
    failed: int


def _start_batch(conn, source: str, target: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO etl.batch_log (source, target) VALUES (%s, %s) RETURNING batch_id",
                    (source, target))
        batch_id = cur.fetchone()[0]
    conn.commit()  # commit now so a FAILED status survives a rollback of the load
    return batch_id


def _fail_batch(conn, batch_id: int, err: Exception) -> None:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("UPDATE etl.batch_log SET status='FAILED', error_message=%s, finished_at=now() "
                    "WHERE batch_id=%s", (str(err)[:2000], batch_id))
    conn.commit()


def _stage_prices(cur, batch_id, source, rows):
    execute_values(
        cur,
        "INSERT INTO staging.stg_price (batch_id, source, symbol, price_date, price, currency, raw_payload) VALUES %s",
        [(batch_id, source, r["symbol"], r["price_date"], r["price"], r["currency"], Json(r["raw"])) for r in rows],
    )


def _stage_positions(cur, batch_id, source, rows):
    execute_values(
        cur,
        "INSERT INTO staging.stg_position (batch_id, source, position_id, book, symbol, quantity, avg_cost, raw_payload) VALUES %s",
        [(batch_id, source, r["position_id"], r["book"], r["symbol"], r["quantity"], r["avg_cost"], Json(r["raw"]))
         for r in rows],
    )


def _run(conn, source, target, rows, stage_fn, log_q, upsert_q) -> BatchResult:
    batch_id = _start_batch(conn, source, target)
    try:
        with conn.cursor() as cur:
            if rows:
                stage_fn(cur, batch_id, source, rows)
            cur.execute(Q[log_q], {"batch_id": batch_id})
            failed = cur.rowcount
            cur.execute(Q[upsert_q], {"batch_id": batch_id})
            flags = [r[0] for r in cur.fetchall()]
            inserted, updated = sum(flags), len(flags) - sum(flags)
            cur.execute(
                "UPDATE etl.batch_log SET status='SUCCESS', rows_staged=%s, rows_inserted=%s, "
                "rows_updated=%s, rows_failed=%s, finished_at=now() WHERE batch_id=%s",
                (len(rows), inserted, updated, failed, batch_id),
            )
        conn.commit()
    except Exception as exc:
        _fail_batch(conn, batch_id, exc)
        raise
    res = BatchResult(batch_id, source, target, len(rows), inserted, updated, failed)
    log.info("batch %s %s/%s: staged=%s inserted=%s updated=%s failed=%s",
             batch_id, source, target, res.staged, inserted, updated, failed)
    return res


def load_prices(conn, source: str, rows: list[dict]) -> BatchResult:
    return _run(conn, source, "PRICE", rows, _stage_prices, "log_failed_prices", "upsert_prices")


def load_positions(conn, source: str, rows: list[dict]) -> BatchResult:
    return _run(conn, source, "POSITION", rows, _stage_positions, "log_failed_positions", "upsert_positions")
