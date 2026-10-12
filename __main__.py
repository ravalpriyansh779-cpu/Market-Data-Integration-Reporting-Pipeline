"""CLI:  python -m marketdata init | run | report | mock-api"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from . import config, ingest_api, ingest_csv, mock_api, pipeline, reports
from .db import connect, ensure_database, init_schema
from .sample_data import last_business_day

log = logging.getLogger("marketdata")


def cmd_init(args):
    ensure_database(config.DATABASE_URL)
    with connect() as conn:
        init_schema(conn)
    log.info("schema ready")


def cmd_run(args):
    ensure_database(config.DATABASE_URL)
    conn = connect()
    init_schema(conn)
    results, failures = [], 0

    server = mock_api.serve(0) if args.mock_api else None
    api_url = f"http://127.0.0.1:{server.server_address[1]}" if server else config.API_BASE_URL
    as_of = last_business_day(date.today())
    try:
        if not args.skip_api:
            try:
                recs = list(ingest_api.fetch_prices(api_url, as_of - timedelta(days=args.api_lookback_days),
                                                    as_of, config.API_KEY))
                results.append(pipeline.load_prices(conn, "API", ingest_api.to_staging_rows(recs)))
            except Exception as exc:  # one failing source must not block the others
                failures += 1
                log.error("API ingestion failed: %s", exc)
        for fn, path, label in ((pipeline.load_prices, args.prices_csv, "prices"),
                                (pipeline.load_positions, args.positions_csv, "positions")):
            try:
                rows = (ingest_csv.price_rows if label == "prices" else ingest_csv.position_rows)(path)
                results.append(fn(conn, "CSV", rows))
            except Exception as exc:
                failures += 1
                log.error("CSV %s ingestion failed: %s", label, exc)
    finally:
        if server:
            server.shutdown()

    report_date = date.fromisoformat(args.report_date) if args.report_date else reports.default_report_date(conn)
    if report_date is None:
        log.error("no prices loaded; cannot build reports")
        return 1
    paths = reports.build_reports(conn, report_date, args.out_dir)
    print(f"\nReport date: {report_date}")
    for r in results:
        print(f"  batch {r.batch_id:>3} {r.source}/{r.target:<8} staged={r.staged:<5} inserted={r.inserted:<5} "
              f"updated={r.updated:<4} failed={r.failed}")
    print("Reports:")
    for p in paths.values():
        print(f"  {p}")
    return 1 if failures else 0


def cmd_report(args):
    with connect() as conn:
        d = date.fromisoformat(args.report_date) if args.report_date else reports.default_report_date(conn)
        paths = reports.build_reports(conn, d, args.out_dir)
    for p in paths.values():
        print(p)


def cmd_mock_api(args):
    import threading
    srv = mock_api.serve(args.port)
    print(f"Mock market API on http://127.0.0.1:{srv.server_address[1]}  (Ctrl+C to stop)")
    threading.Event().wait()


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="marketdata")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create database objects").set_defaults(fn=cmd_init)

    r = sub.add_parser("run", help="ingest API + CSV, validate, upsert, build reports")
    r.add_argument("--mock-api", action="store_true", help="use the built-in mock REST API")
    r.add_argument("--skip-api", action="store_true")
    r.add_argument("--api-lookback-days", type=int, default=config.API_LOOKBACK_DAYS)
    r.add_argument("--prices-csv", default=config.PRICES_CSV)
    r.add_argument("--positions-csv", default=config.POSITIONS_CSV)
    r.add_argument("--report-date")
    r.add_argument("--out-dir", default=config.OUTPUT_DIR)
    r.set_defaults(fn=cmd_run)

    p = sub.add_parser("report", help="rebuild reports from loaded data")
    p.add_argument("--report-date")
    p.add_argument("--out-dir", default=config.OUTPUT_DIR)
    p.set_defaults(fn=cmd_report)

    m = sub.add_parser("mock-api", help="run the mock REST API standalone")
    m.add_argument("--port", type=int, default=8765)
    m.set_defaults(fn=cmd_mock_api)

    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
