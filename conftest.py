import sys
from pathlib import Path

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marketdata import config  # noqa: E402
from marketdata.db import connect, ensure_database, init_schema  # noqa: E402


@pytest.fixture(scope="session")
def _db():
    try:
        ensure_database(config.TEST_DATABASE_URL)
        conn = connect(config.TEST_DATABASE_URL)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable for tests: {exc}")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def conn(_db):
    _db.rollback()
    with _db.cursor() as cur:
        cur.execute("TRUNCATE core.commodity_price, core.position, staging.stg_price, staging.stg_position, "
                    "etl.failed_record, etl.batch_log RESTART IDENTITY CASCADE")
    _db.commit()
    return _db
