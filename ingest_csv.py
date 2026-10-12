"""CSV feed readers. Values are passed through untouched; validation happens in SQL."""
from __future__ import annotations

import csv
from pathlib import Path

PRICE_COLS = ["date", "symbol", "price", "currency"]
POSITION_COLS = ["position_id", "book", "symbol", "quantity", "avg_cost"]


def read_csv(path: str | Path, required: list[str]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in header]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}; found {header}")
        reader.fieldnames = header
        return [{k: (v if v is not None else None) for k, v in row.items() if k in required}
                for row in reader]


def price_rows(path) -> list[dict]:
    return [{"symbol": r["symbol"], "price_date": r["date"], "price": r["price"],
             "currency": r["currency"], "raw": r} for r in read_csv(path, PRICE_COLS)]


def position_rows(path) -> list[dict]:
    return [{"position_id": r["position_id"], "book": r["book"], "symbol": r["symbol"],
             "quantity": r["quantity"], "avg_cost": r["avg_cost"], "raw": r}
            for r in read_csv(path, POSITION_COLS)]
