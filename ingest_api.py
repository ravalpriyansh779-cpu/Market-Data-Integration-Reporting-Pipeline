"""Third-party REST API client: paginated fetch with retries, mapped to raw staging rows."""
from __future__ import annotations

from datetime import date
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch_prices(base_url: str, date_from: date, date_to: date, api_key: str = "",
                 timeout: float = 15.0) -> Iterator[dict]:
    session = _session()
    headers = {"X-API-Key": api_key} if api_key else {}
    page = 1
    while True:
        resp = session.get(
            f"{base_url.rstrip('/')}/v1/prices",
            params={"from": date_from.isoformat(), "to": date_to.isoformat(), "page": page},
            headers=headers, timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        yield from payload["data"]
        if page >= int(payload.get("total_pages", 1)):
            return
        page += 1


def _s(v):
    return None if v is None else str(v)


def to_staging_rows(records) -> list[dict]:
    """Keep values as raw strings; all validation happens in SQL."""
    return [
        {"symbol": _s(r.get("symbol")), "price_date": _s(r.get("date")),
         "price": _s(r.get("price")), "currency": _s(r.get("currency")), "raw": r}
        for r in records
    ]
