"""
price_server.py — Tiny HTTP proxy server for the standalone HTML dashboards.

Run: python price_server.py
Then open standalone-alerts-full.html in your browser.
Proxies Yahoo Finance requests to avoid browser CORS restrictions.
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.error
import urllib.request

PORT = int(os.getenv("PRICE_SERVER_PORT", "8080"))

# Supported symbol → display name mapping
SYMBOL_MAP: dict[str, str] = {
    # Commodities
    "GC=F":  "Gold",
    "SI=F":  "Silver",
    "CL=F":  "Crude Oil",
    "NG=F":  "Natural Gas",
    "HG=F":  "Copper",
    # Stocks
    "NVDA":  "NVIDIA",
    "TSLA":  "Tesla",
    "AAPL":  "Apple",
    "GOOGL": "Google",
    "MSFT":  "Microsoft",
    "AMZN":  "Amazon",
    "META":  "Meta",
    "ORCL":  "Oracle",
    "NFLX":  "Netflix",
    # Indices
    "^GSPC": "S&P 500",
    "^DJI":  "Dow Jones",
    "^IXIC": "NASDAQ",
}


def _fetch_yahoo(symbol: str) -> float | None:
    """Fetch the latest price for a symbol from Yahoo Finance."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.request.quote(symbol)}?interval=1d&range=1d"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data  = json.loads(resp.read())
            price = (
                data.get("chart", {})
                    .get("result", [{}])[0]
                    .get("meta", {})
                    .get("regularMarketPrice")
            )
            return float(price) if price is not None else None
    except Exception as exc:
        print(f"  [price_server] Error fetching {symbol}: {exc}")
        return None


def _json_response(handler, status: int, body: dict) -> None:
    """Helper to write a JSON response."""
    payload = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)


class CORSRequestHandler(SimpleHTTPRequestHandler):
    """HTTP handler that proxies /api/<SYMBOL> to Yahoo Finance."""

    def log_message(self, fmt, *args):
        # Suppress noisy access logs for static files; keep API logs
        if self.path.startswith("/api/"):
            print(f"  [price_server] {fmt % args}")

    def do_OPTIONS(self):
        """Pre-flight CORS response."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/symbols":
            # Return the full symbol map so the front-end can build dropdowns
            _json_response(self, 200, {"symbols": SYMBOL_MAP})
            return

        if self.path.startswith("/api/"):
            symbol = urllib.request.unquote(self.path[5:])  # strip /api/
            if symbol not in SYMBOL_MAP:
                _json_response(self, 404, {
                    "error": f"Unknown symbol '{symbol}'.",
                    "supported": list(SYMBOL_MAP.keys()),
                })
                return

            price = _fetch_yahoo(symbol)
            if price is None:
                _json_response(self, 502, {
                    "error": f"Failed to fetch price for '{symbol}'. Yahoo Finance may be unavailable.",
                })
                return

            _json_response(self, 200, {
                "symbol": symbol,
                "name":   SYMBOL_MAP[symbol],
                "price":  price,
            })
            return

        # Serve static files for everything else
        super().do_GET()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


if __name__ == "__main__":
    print(f"  Price proxy server running at http://localhost:{PORT}")
    print("  Keep this window open while using the HTML dashboards.")
    print(f"  Supported symbols: {', '.join(SYMBOL_MAP.keys())}")
    HTTPServer(("", PORT), CORSRequestHandler).serve_forever()
