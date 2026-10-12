"""Deterministic synthetic commodity prices, shared by the CSV generator and the mock API."""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

# symbol: (base price, swing, phase)
SYMBOLS = {
    "WTI": (72.0, 0.10, 0.3), "BRENT": (76.0, 0.10, 0.5), "NG": (3.1, 0.18, 1.1),
    "GOLD": (2350.0, 0.05, 2.0), "SILVER": (29.0, 0.09, 2.4), "COPPER": (4.3, 0.07, 3.0),
    "CORN": (4.4, 0.08, 4.1), "WHEAT": (5.9, 0.09, 4.6), "SOY": (11.8, 0.07, 5.2),
    "SUGAR": (0.19, 0.10, 5.9),
}


def synthetic_price(symbol: str, d: date) -> float:
    base, swing, phase = SYMBOLS[symbol]
    h = int(hashlib.md5(f"{symbol}{d.isoformat()}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    trend = math.sin(d.toordinal() / 25.0 + phase)
    return round(base * (1 + swing * trend + 0.012 * (h - 0.5)), 4)


def business_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def last_business_day(on_or_before: date) -> date:
    d = on_or_before
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
