"""Tiny stand-in for a third-party commodity price REST API (stdlib only).

GET /v1/prices?from=YYYY-MM-DD&to=YYYY-MM-DD&page=N  ->
    {"data": [{"symbol","date","price","currency"}...], "page": N, "total_pages": M}

A few deliberately bad records are appended so the failed-record path is exercised.
"""
from __future__ import annotations

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .sample_data import SYMBOLS, business_days, synthetic_price

PAGE_SIZE = 100


def build_records(d_from: date, d_to: date) -> list[dict]:
    recs = [
        {"symbol": s, "date": d.isoformat(), "price": synthetic_price(s, d), "currency": "USD"}
        for d in business_days(d_from, d_to) for s in SYMBOLS
    ]
    if recs:
        last = recs[-1]["date"]
        recs += [
            {"symbol": "WTI", "date": last, "price": -5.0, "currency": "USD"},        # NON_POSITIVE_PRICE
            {"symbol": "XYZ", "date": last, "price": 10.0, "currency": "USD"},        # UNKNOWN_SYMBOL
            {"symbol": "GOLD", "date": "2026-13-40", "price": 2400.0, "currency": "USD"},  # BAD_DATE
            {"symbol": "NG", "date": last, "price": None, "currency": "USD"},         # BAD_PRICE
            {"symbol": "CORN", "date": last, "price": 4.5, "currency": "EUR"},        # CURRENCY_MISMATCH
        ]
    return recs


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/v1/prices":
            self.send_error(404)
            return
        q = parse_qs(url.query)
        try:
            d_from = date.fromisoformat(q["from"][0])
            d_to = date.fromisoformat(q["to"][0])
            page = int(q.get("page", ["1"])[0])
        except (KeyError, ValueError):
            self.send_error(400, "from/to (YYYY-MM-DD) required")
            return
        recs = build_records(d_from, d_to)
        total_pages = max(1, -(-len(recs) // PAGE_SIZE))
        body = json.dumps({
            "data": recs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE],
            "page": page, "total_pages": total_pages,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Start the mock API in a background thread; port=0 picks a free port."""
    server = ThreadingHTTPServer((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    srv = serve()
    print(f"Mock market API on http://127.0.0.1:{srv.server_address[1]}  (Ctrl+C to stop)")
    threading.Event().wait()
