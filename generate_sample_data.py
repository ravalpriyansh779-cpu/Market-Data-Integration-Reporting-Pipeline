"""Regenerate data/sample_prices.csv and data/sample_positions.csv (deterministic)."""
import csv
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marketdata.sample_data import SYMBOLS, business_days, synthetic_price  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

# ---- prices (vendor CSV feed) ----
rows = [[d.isoformat(), s, f"{synthetic_price(s, d):.4f}", "USD"]
        for d in business_days(date(2026, 6, 1), date(2026, 10, 9)) for s in SYMBOLS]
rows += [
    ["2026-10-09", "wti", "71.9000", "USD"],     # lowercase -> normalised, then duplicate of WTI (later wins)
    ["2026-10-09", "", "50.0000", "USD"],        # MISSING_SYMBOL
    ["2026-10-08", "GOLD", "abc", "USD"],        # BAD_PRICE
    ["2026-10-08", "SILVER", "-12.5", "USD"],    # NON_POSITIVE_PRICE
    ["2026-10-07", "ZZZ", "10.0", "USD"],        # UNKNOWN_SYMBOL
    ["2026-02-30", "WHEAT", "5.9", "USD"],       # BAD_DATE
    ["2099-01-01", "SOY", "11.0", "USD"],        # FUTURE_DATE
]
with open(DATA / "sample_prices.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "symbol", "price", "currency"])
    w.writerows(rows)

# ---- positions ----
rnd = random.Random(42)
books = {"ENERGY-DESK": ["WTI", "BRENT", "NG"], "METALS-DESK": ["GOLD", "SILVER", "COPPER"],
         "AGRI-DESK": ["CORN", "WHEAT", "SOY", "SUGAR"]}
pos = []
n = 1
for book, syms in books.items():
    for s in syms:
        for _ in range(3):
            base = synthetic_price(s, date(2026, 9, 1))
            qty = rnd.choice([-1, 1]) * rnd.randrange(50, 800, 10) * (10 if s in ("CORN", "WHEAT", "SOY") else 1)
            cost = round(base * rnd.uniform(0.92, 1.08), 4)
            pos.append([f"P{n:04d}", book, s, qty, cost])
            n += 1
pos += [
    ["", "ENERGY-DESK", "WTI", "100", "70.0"],       # MISSING_POSITION_ID
    ["P9001", "METALS-DESK", "PLAT", "10", "900.0"], # UNKNOWN_SYMBOL
    ["P9002", "AGRI-DESK", "CORN", "ten", "4.2"],    # BAD_QUANTITY
    ["P9003", "AGRI-DESK", "SOY", "100", "0"],       # BAD_AVG_COST
    ["P0001", "ENERGY-DESK", "WTI", "999", "71.0"],  # duplicate id: later record wins
]
with open(DATA / "sample_positions.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["position_id", "book", "symbol", "quantity", "avg_cost"])
    w.writerows(pos)
print(f"wrote {len(rows)} price rows, {len(pos)} position rows")
