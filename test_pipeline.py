from datetime import date, timedelta

from marketdata import ingest_api, ingest_csv, mock_api, pipeline


def price(symbol, d, p, cur="USD"):
    return {"symbol": symbol, "price_date": d, "price": p, "currency": cur,
            "raw": {"symbol": symbol, "date": d, "price": p, "currency": cur}}


def fetch(conn, sql, *args):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def test_validation_flags_each_defect(conn):
    today = date.today()
    rows = [
        price("WTI", "2026-01-05", "70.5"),                     # ok
        price(" wti ", "2026-01-06", "71"),                      # ok (normalised)
        price("", "2026-01-05", "70"),                           # MISSING_SYMBOL
        price("NOPE", "2026-01-05", "70"),                       # UNKNOWN_SYMBOL
        price("WTI", "2026-02-30", "70"),                        # BAD_DATE
        price("WTI", (today + timedelta(days=3)).isoformat(), "70"),  # FUTURE_DATE
        price("WTI", "2026-01-07", "abc"),                       # BAD_PRICE
        price("WTI", "2026-01-08", "0"),                         # NON_POSITIVE_PRICE
        price("WTI", "2026-01-09", "1e12"),                      # PRICE_OUT_OF_RANGE
        price("WTI", "2026-01-12", "70", "EUR"),                 # CURRENCY_MISMATCH
        price("GOLD", "2026-01-05", "2300"),                     # superseded...
        price("GOLD", "2026-01-05", "2310"),                     # ...by this (DUPLICATE_IN_BATCH on the first)
    ]
    res = pipeline.load_prices(conn, "CSV", rows)
    assert (res.staged, res.inserted, res.updated, res.failed) == (12, 3, 0, 9)
    codes = {c for (c,) in fetch(conn, "SELECT error_code FROM etl.failed_record")}
    assert codes == {"MISSING_SYMBOL", "UNKNOWN_SYMBOL", "BAD_DATE", "FUTURE_DATE", "BAD_PRICE",
                     "NON_POSITIVE_PRICE", "PRICE_OUT_OF_RANGE", "CURRENCY_MISMATCH", "DUPLICATE_IN_BATCH"}
    assert fetch(conn, "SELECT price FROM core.commodity_price WHERE symbol='GOLD'")[0][0] == 2310  # last wins


def test_upsert_is_idempotent_and_updates_on_change(conn):
    assert pipeline.load_prices(conn, "CSV", [price("WTI", "2026-01-05", "70")]).inserted == 1
    r = pipeline.load_prices(conn, "CSV", [price("WTI", "2026-01-05", "70")])
    assert (r.inserted, r.updated) == (0, 0)
    r = pipeline.load_prices(conn, "CSV", [price("WTI", "2026-01-05", "71")])
    assert (r.inserted, r.updated) == (0, 1)
    assert fetch(conn, "SELECT price FROM core.commodity_price")[0][0] == 71


def test_failed_records_are_deduplicated_with_occurrence_count(conn):
    bad = [price("WTI", "2026-01-05", "-1")]
    pipeline.load_prices(conn, "CSV", bad)
    pipeline.load_prices(conn, "CSV", bad)
    rows = fetch(conn, "SELECT error_code, occurrences, resolved FROM etl.failed_record")
    assert rows == [("NON_POSITIVE_PRICE", 2, False)]
    with conn.cursor() as cur:
        cur.execute("UPDATE etl.failed_record SET resolved = TRUE")
    conn.commit()
    pipeline.load_prices(conn, "CSV", bad)  # recurrence re-opens it
    assert fetch(conn, "SELECT resolved FROM etl.failed_record")[0][0] is False


def test_positions_validation_and_upsert(conn):
    def pos(i, b, s, q, c):
        return {"position_id": i, "book": b, "symbol": s, "quantity": q, "avg_cost": c,
                "raw": {"position_id": i, "book": b, "symbol": s, "quantity": q, "avg_cost": c}}
    rows = [pos("P1", "B", "WTI", "100", "70"), pos("P1", "B", "WTI", "150", "70"),   # dup -> last wins
            pos("", "B", "WTI", "1", "1"), pos("P2", "B", "PLAT", "1", "1"),
            pos("P3", "B", "WTI", "x", "1"), pos("P4", "B", "WTI", "1", "0")]
    r = pipeline.load_positions(conn, "CSV", rows)
    assert (r.inserted, r.failed) == (1, 5)
    assert fetch(conn, "SELECT quantity FROM core.position WHERE position_id='P1'")[0][0] == 150


def test_exposure_and_pnl_math(conn):
    pipeline.load_prices(conn, "CSV", [price("WTI", "2026-03-02", "70"), price("WTI", "2026-03-03", "72"),
                                       price("WTI", "2026-03-04", "75")])
    pipeline.load_positions(conn, "CSV", [
        {"position_id": "L", "book": "B", "symbol": "WTI", "quantity": "100", "avg_cost": "68", "raw": {"id": "L"}},
        {"position_id": "S", "book": "B", "symbol": "WTI", "quantity": "-50", "avg_cost": "74", "raw": {"id": "S"}}])
    rows = fetch(conn, "SELECT quantity, exposure, unrealized_pnl, daily_pnl, is_stale "
                       "FROM core.fn_exposure_pnl(%s) ORDER BY quantity DESC", date(2026, 3, 4))
    (lq, lexp, lun, ld, lstale), (sq, sexp, sun, sd, sstale) = rows
    assert (lexp, lun, ld, lstale) == (7500, 700, 300, False)        # 100 * 75, (75-68)*100, (75-72)*100
    assert (sexp, sun, sd, sstale) == (-3750, -50, -150, False)      # short: P&L signs flip
    # report date after the last price -> stale, daily P&L suppressed
    stale = fetch(conn, "SELECT daily_pnl, is_stale, price_date FROM core.fn_exposure_pnl(%s) LIMIT 1",
                  date(2026, 3, 6))[0]
    assert stale == (None, True, date(2026, 3, 4))


def test_api_price_preferred_over_csv(conn):
    pipeline.load_prices(conn, "CSV", [price("GOLD", "2026-03-04", "2300")])
    pipeline.load_prices(conn, "API", [price("GOLD", "2026-03-04", "2310")])
    pipeline.load_positions(conn, "CSV", [
        {"position_id": "G", "book": "B", "symbol": "GOLD", "quantity": "1", "avg_cost": "2000", "raw": {"id": "G"}}])
    assert fetch(conn, "SELECT mkt_price FROM core.fn_exposure_pnl(%s)", date(2026, 3, 4))[0][0] == 2310


def test_mock_api_roundtrip_paginates_and_includes_defects():
    server = mock_api.serve(0)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        recs = list(ingest_api.fetch_prices(url, date(2026, 9, 1), date(2026, 9, 30)))
    finally:
        server.shutdown()
    assert len(recs) > mock_api.PAGE_SIZE            # more than one page was fetched
    assert any(r["symbol"] == "XYZ" for r in recs)
    staged = ingest_api.to_staging_rows(recs)
    assert all(isinstance(r["price"], (str, type(None))) for r in staged)


def test_csv_reader_rejects_missing_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,symbol\n2026-01-01,WTI\n")
    try:
        ingest_csv.price_rows(p)
    except ValueError as exc:
        assert "missing column" in str(exc)
    else:
        raise AssertionError("expected ValueError")
