# Market Data Integration & Reporting Pipeline

Python · SQL · PostgreSQL · Third-Party Integration · ETL · Reports

Imports commodity prices from an external REST API and a CSV feed into normalized staging tables,
validates and upserts them in SQL (logging every rejected record for defect follow-up), and produces a
daily exposure and P&L report as CSV and PDF, built entirely from SQL.

```
 REST API ──► ingest_api.py ─┐                                   ┌─► core.commodity_price ─┐
 (paged, retries)            ├─► staging.stg_price / stg_position ┤                         ├─► core.fn_exposure_pnl()
 prices.csv ─► ingest_csv.py ┘   (raw TEXT + JSON payload)        └─► etl.failed_record     │        │
 positions.csv ──────────────────────────────────────────────────►  core.position ─────────┘        ▼
                                  SQL views validate · ON CONFLICT upsert                   CSV + PDF reports
```

## Quick start

```bash
docker compose up -d --wait          # PostgreSQL 16 (or point DATABASE_URL at your own)
pip install -r requirements.txt
python -m marketdata run --mock-api  # ingest API + CSV, validate, upsert, build reports
python -m pytest -q                  # integration tests (creates marketdata_test DB)
python scripts/benchmark.py          # before/after report-query timing on synthetic data
```

Outputs land in `output/<report-date>/`: `daily_exposure_pnl.pdf`, `exposure_pnl_detail.csv`,
`exposure_by_commodity.csv`, `exposure_by_book.csv`, `open_defects.csv`. A sample run is included.

Real provider: set `MARKET_API_URL` / `MARKET_API_KEY` (see `.env.example`) and drop `--mock-api`.
The client expects `GET /v1/prices?from&to&page` returning `{data:[{symbol,date,price,currency}], total_pages}`;
adapt `marketdata/ingest_api.py` for a different payload shape (it is the only provider-specific file).

## How it maps to the resume bullets

| Bullet | Where |
|---|---|
| Third-party integration, REST API + CSV into normalized staging | `ingest_api.py` (pagination, retry/backoff, timeouts), `ingest_csv.py`, `sql/schema/01_schema.sql` (`staging.*`: raw TEXT + JSONB payload, per-batch lineage via `etl.batch_log`) |
| SQL validation and upsert, failed-record logging | `sql/schema/02_validation_views.sql` (all rules in one place), `sql/queries/load.sql` (`INSERT … ON CONFLICT DO UPDATE … WHERE IS DISTINCT FROM`), `etl.failed_record` + `etl.error_code` |
| Daily exposure and P&L reports (CSV/PDF) in SQL | `sql/schema/03_report_functions.sql`, `sql/queries/reports.sql` (`ROLLUP` totals), `marketdata/reports.py` |
| Query optimization via indexing and restructuring | `sql/schema/04_indexes.sql`, `sql/benchmark/naive_exposure.sql` vs `core.fn_exposure_pnl()`, `scripts/benchmark.py` |

## Design notes

**Validation (SQL, not Python).** Staging keeps raw strings, so a bad value can never abort a load. `staging.v_price_checked`
and `v_position_checked` assign each row at most one `error_code`; clean rows are upserted, the rest are logged.
Rules: missing/unknown symbol, bad or future date, non-numeric / non-positive / out-of-range price, currency mismatch,
and in-batch duplicates (last record in the feed wins). Position rules cover id, book, symbol, quantity, and cost.

**Failed-record log for defect resolution.** One row per distinct defect (fingerprint of source + code + payload).
Re-ingesting the same bad row increments `occurrences` instead of duplicating, and re-opens it if it was marked resolved.
Each code has a `suggested_resolution` in `etl.error_code`, exported in `open_defects.csv`. Close a defect with:
`UPDATE etl.failed_record SET resolved = TRUE, resolved_at = now(), resolution_note = '...' WHERE failed_id = 42;`

**Idempotent, auditable loads.** Re-running the pipeline inserts and updates nothing (the `WHERE … IS DISTINCT FROM` guard
skips unchanged rows). Every run writes staged / inserted / updated / failed counts to `etl.batch_log`; a failed batch is
rolled back and recorded as `FAILED`. A failing source (e.g. API down) does not stop the others; exit code is non-zero.

**Report definitions** (USD, positions signed: negative = short)
- exposure = quantity × latest price on or before the report date
- unrealized P&L = (latest price − avg cost) × quantity
- daily P&L = (latest − previous price) × quantity, only when the latest price is dated the report date; otherwise it is
  left blank and the row is flagged stale (`*` in the PDF)
- when API and CSV both carry a (symbol, date), the API value is used (`source_rank`)

**Optimization.** The first-draft query used correlated `max(price_date)` subqueries per position row. The rewrite resolves
the latest two prices once per commodity (`LATERAL` + `DISTINCT ON … LIMIT 2` over a
`(symbol, price_date DESC, source_rank) INCLUDE (price)` index), then joins positions to that small set.
On my sandbox (357k price rows, 20k positions, 100 symbols) the median runtime dropped from about 1.1 s to about 0.09 s,
roughly 12x with identical results. Run `python scripts/benchmark.py` for your own numbers, and quote those on your resume.

## Layout

```
marketdata/   config, db, ingest_api, ingest_csv, pipeline, reports, mock_api, sample_data, __main__ (CLI)
sql/schema/   01 tables · 02 validation views · 03 report function · 04 indexes · 05 reference seed
sql/queries/  load.sql (log + upsert) · reports.sql
sql/benchmark/naive_exposure.sql
scripts/      generate_sample_data.py · benchmark.py
tests/        8 integration tests (validation codes, idempotency, dedupe, P&L math, source priority, API paging)
data/         sample_prices.csv · sample_positions.csv (include deliberate defects)
```

## Known limits

Positions are loaded as a snapshot upsert (removed positions are not deleted). All commodities are USD; a non-USD quote is
rejected as `CURRENCY_MISMATCH` rather than converted. The bundled API is a local mock with synthetic prices.
