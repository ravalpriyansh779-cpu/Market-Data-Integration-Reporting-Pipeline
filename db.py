"""Database helpers: connections, schema bootstrap, and a tiny named-query loader."""
from __future__ import annotations

import re
from pathlib import Path

import psycopg2

from . import config

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
_NAME_RE = re.compile(r"^--\s*name:\s*(\w+)\s*$")


def connect(dsn: str | None = None):
    return psycopg2.connect(dsn or config.DATABASE_URL)


def load_queries(relative_path: str) -> dict[str, str]:
    """Parse a .sql file into {name: sql} using '-- name: foo' markers."""
    queries: dict[str, list[str]] = {}
    current = None
    for line in (SQL_DIR / relative_path).read_text().splitlines():
        m = _NAME_RE.match(line)
        if m:
            current = m.group(1)
            queries[current] = []
        elif current is not None:
            queries[current].append(line)
    return {k: "\n".join(v).strip().rstrip(";") for k, v in queries.items()}


def init_schema(conn) -> None:
    """Idempotently create schemas, tables, views, functions, indexes and reference data."""
    for path in sorted((SQL_DIR / "schema").glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text())
    conn.commit()


def ensure_database(dsn: str) -> None:
    """Create the database named in `dsn` if it does not exist (needs CREATEDB)."""
    from psycopg2 import sql
    from psycopg2.extensions import parse_dsn, make_dsn

    params = parse_dsn(dsn)
    dbname = params["dbname"]
    admin = psycopg2.connect(make_dsn(dsn, dbname="postgres"))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    admin.close()
