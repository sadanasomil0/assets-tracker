"""
backend/main.py — FastAPI server exposing the alert engine via REST & WebSocket.

Endpoints:
    GET  /                        — health check
    GET  /status                  — uptime, asset counts, alert stats
    GET  /assets/available        — list all supported assets  ← MUST be before /assets/{name}
    GET  /assets                  — list tracked assets
    POST /assets                  — add / update a tracked asset
    DELETE /assets/{name}         — stop tracking an asset
    GET  /history                 — last 100 alert events
    WS   /ws                      — real-time price & alert stream
"""

import asyncio
import json
import logging
import sys
import os
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque

import aiohttp
import uvicorn
import websockets
import yfinance as yf
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Allow importing root-level config when run from backend/ ─────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config as cfg  # noqa: E402  (import after sys.path fix)

PORT = int(os.getenv("BACKEND_PORT", "8000"))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("backend")

# ─── Pydantic Models ──────────────────────────────────────────────────────────


class RangeState(str, Enum):
    OUTSIDE = "OUTSIDE"
    INSIDE  = "INSIDE"


class AssetAlert(BaseModel):
    name:            str
    min_price:       float
    max_price:       float
    state:           RangeState = RangeState.OUTSIDE
    last_price:      float | None = None
    last_alert_time: str | None = None


class AddAssetRequest(BaseModel):
    name:      str
    min_price: float
    max_price: float


class AlertEvent(BaseModel):
    asset_name: str
    price:      float
    min_price:  float
    max_price:  float
    timestamp:  str


# ─── Alert Engine ─────────────────────────────────────────────────────────────


class AlertEngine:
    """Thread-safe alert engine with cooldown and in-memory history."""

    def __init__(self) -> None:
        self._lock     = threading.Lock()
        self._assets:   dict[str, dict]    = {}
        self._callbacks: list              = []
        self._history:  Deque[AlertEvent]  = deque(maxlen=cfg.ALERT_HISTORY_MAX)
        self._start_time = datetime.now(timezone.utc)

    # ── Asset management ─────────────────────────────────────────────────

    def add_asset(self, name: str, min_price: float, max_price: float) -> AssetAlert:
        name = name.upper()
        with self._lock:
            if name in self._assets:
                self._assets[name].update({
                    "min_price": min_price,
                    "max_price": max_price,
                    "state":     RangeState.OUTSIDE,
                })
                log.info("Updated range for %s: $%.4f – $%.4f", name, min_price, max_price)
            else:
                self._assets[name] = {
                    "name":            name,
                    "min_price":       min_price,
                    "max_price":       max_price,
                    "state":           RangeState.OUTSIDE,
                    "last_price":      None,
                    "last_alert_time": None,
                }
                log.info("Added asset %s: $%.4f – $%.4f", name, min_price, max_price)
            return AssetAlert(**self._assets[name])

    def remove_asset(self, name: str) -> bool:
        name = name.upper()
        with self._lock:
            if name in self._assets:
                del self._assets[name]
                log.info("Removed asset %s", name)
                return True
            return False

    def get_tracked_assets(self) -> list[AssetAlert]:
        with self._lock:
            return [AssetAlert(**a) for a in self._assets.values()]

    def get_active_assets(self) -> dict[str, tuple[float, float]]:
        with self._lock:
            return {n: (a["min_price"], a["max_price"]) for n, a in self._assets.items()}

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    # ── Price evaluation ─────────────────────────────────────────────────

    def on_price_update(self, name: str, price: float) -> AlertEvent | None:
        name = name.upper()
        with self._lock:
            asset = self._assets.get(name)
            if not asset:
                return None

            asset["last_price"] = price
            in_range = asset["min_price"] <= price <= asset["max_price"]

            if in_range and asset["state"] == RangeState.OUTSIDE:
                # Cooldown check
                if asset["last_alert_time"] is not None:
                    last_t  = datetime.fromisoformat(asset["last_alert_time"])
                    elapsed = (datetime.now(timezone.utc) - last_t).total_seconds()
                    if elapsed < cfg.ALERT_COOLDOWN_SECONDS:
                        asset["state"] = RangeState.INSIDE
                        return None

                asset["state"] = RangeState.INSIDE
                now = datetime.now(timezone.utc)
                asset["last_alert_time"] = now.isoformat()
                event = AlertEvent(
                    asset_name=name,
                    price=price,
                    min_price=asset["min_price"],
                    max_price=asset["max_price"],
                    timestamp=now.isoformat(),
                )
                self._history.append(event)
                log.info(
                    "🔔 ALERT: %s entered range [$%.4f – $%.4f] at $%.4f",
                    name, asset["min_price"], asset["max_price"], price,
                )
                self._notify(event)
                return event

            elif not in_range and asset["state"] == RangeState.INSIDE:
                asset["state"] = RangeState.OUTSIDE
                log.debug("%s exited range at $%.4f — state reset", name, price)
            return None

    # ── Subscriptions ─────────────────────────────────────────────────────

    def subscribe(self, callback) -> None:
        self._callbacks.append(callback)

    def _notify(self, event: AlertEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as exc:
                log.warning("Alert callback error: %s", exc)

    # ── Stats ─────────────────────────────────────────────────────────────

    def uptime_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()


engine = AlertEngine()

# Load defaults from shared config
for _name, (_min, _max) in cfg.DEFAULT_RANGES.items():
    engine.add_asset(_name, _min, _max)

# ─── WebSocket Manager ────────────────────────────────────────────────────────


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        log.info("WS client connected (total: %d)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        log.info("WS client disconnected (total: %d)", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        """Broadcast to all connected WebSocket clients; remove dead ones."""
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()

# ── Bridge: sync alert callback → async broadcast ────────────────────────────
# We schedule the coroutine on the running event loop from a sync context.
_loop: asyncio.AbstractEventLoop | None = None


def _on_alert(event: AlertEvent) -> None:
    """Sync callback wired into the alert engine — schedules async broadcast."""
    if _loop is not None and _loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "alert", "data": event.model_dump()}),
            _loop,
        )


def _on_price_update(name: str, price: float) -> None:
    """Broadcast every price tick to WebSocket clients."""
    if _loop is not None and _loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "price_update",
                "data": {
                    "name":      name,
                    "price":     price,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }),
            _loop,
        )


engine.subscribe(_on_alert)

# ─── FastAPI App ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    log.info("Starting background price fetchers…")
    t1 = asyncio.create_task(poll_stocks(),   name="stock_poller")
    t2 = asyncio.create_task(stream_crypto(), name="crypto_streamer")
    yield
    t1.cancel()
    t2.cancel()
    await asyncio.gather(t1, t2, return_exceptions=True)
    log.info("Backend shut down cleanly.")


app = FastAPI(
    title="Price Alert API",
    version="2.0.0",
    description="Real-time multi-asset price alert engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── REST Endpoints ───────────────────────────────────────────────────────────


@app.get("/")
async def root() -> dict:
    return {"status": "running", "message": "Price Alert API v2", "docs": "/docs"}


@app.get("/status")
async def status() -> dict:
    uptime   = engine.uptime_seconds()
    hours    = int(uptime // 3600)
    minutes  = int((uptime % 3600) // 60)
    seconds  = int(uptime % 60)
    tracked  = engine.get_tracked_assets()
    crypto   = sum(1 for a in tracked if a.name in cfg.BINANCE_SYMBOLS)
    history  = engine.get_history()
    return {
        "uptime":           f"{hours}h {minutes}m {seconds}s",
        "tracked_assets":   len(tracked),
        "crypto_assets":    crypto,
        "stock_assets":     len(tracked) - crypto,
        "alerts_fired":     len(history),
        "cooldown_seconds": cfg.ALERT_COOLDOWN_SECONDS,
        "ws_clients":       len(manager._connections),
    }


# ⚠️ /assets/available MUST be declared before /assets/{name} to avoid route shadowing
@app.get("/assets/available")
async def available_assets() -> dict:
    commodities = [k for k in cfg.YFINANCE_TICKERS if k in ("GOLD", "SILVER", "CRUDE_OIL")]
    stocks      = [k for k in cfg.YFINANCE_TICKERS if k not in commodities]
    return {
        "commodities": sorted(commodities),
        "stocks":      sorted(stocks),
        "crypto":      sorted(cfg.BINANCE_SYMBOLS.keys()),
        "all":         sorted(cfg.ALL_ASSETS),
    }


@app.get("/assets")
async def list_assets() -> list[AssetAlert]:
    return engine.get_tracked_assets()


@app.post("/assets", status_code=201)
async def add_asset(req: AddAssetRequest) -> AssetAlert:
    name = req.name.upper()
    if name not in cfg.ALL_ASSETS:
        raise HTTPException(400, f"Unknown asset '{name}'. See /assets/available.")
    if req.min_price >= req.max_price:
        raise HTTPException(400, "min_price must be strictly less than max_price.")
    return engine.add_asset(name, req.min_price, req.max_price)


@app.delete("/assets/{name}")
async def remove_asset(name: str) -> dict:
    if not engine.remove_asset(name.upper()):
        raise HTTPException(404, f"Asset '{name.upper()}' is not being tracked.")
    return {"message": f"Asset {name.upper()} removed successfully."}


@app.get("/history")
async def alert_history() -> list[dict]:
    """Return up to the last 100 alert events (newest first)."""
    events = engine.get_history()
    events.reverse()
    return [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in events]


# ─── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    # Send a welcome snapshot so the client knows what's tracked
    await websocket.send_json({
        "type": "snapshot",
        "data": [a.model_dump() for a in engine.get_tracked_assets()],
    })
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


# ─── Background Price Fetchers ────────────────────────────────────────────────


async def poll_stocks() -> None:
    """Poll yfinance for stocks/commodities on a fixed interval."""
    log.info("Stock poller started (interval=%ds)", cfg.STOCK_POLL_INTERVAL)
    while True:
        try:
            active = engine.get_active_assets()
            to_fetch = {n: cfg.YFINANCE_TICKERS[n] for n in cfg.YFINANCE_TICKERS if n in active}
            if to_fetch:
                data = await asyncio.to_thread(_fetch_stocks_sync, to_fetch)
                for name, price in data.items():
                    if price:
                        engine.on_price_update(name, price)
                        _on_price_update(name, price)
        except Exception as exc:
            log.warning("Stock poller error: %s", exc)
        await asyncio.sleep(cfg.STOCK_POLL_INTERVAL)


def _fetch_stocks_sync(to_fetch: dict[str, str]) -> dict[str, float | None]:
    """Sync yfinance fetch helper (runs in thread pool)."""
    results: dict[str, float | None] = {}
    for name, ticker_str in to_fetch.items():
        try:
            fi    = yf.Ticker(ticker_str).fast_info
            price = None
            try:
                price = fi.last_price
            except AttributeError:
                pass
            if not price:
                try:
                    price = fi.lastPrice
                except AttributeError:
                    pass
            results[name] = float(price) if price and float(price) > 0 else None
        except Exception as exc:
            log.debug("yfinance error for %s: %s", ticker_str, exc)
            results[name] = None
    return results


async def stream_crypto() -> None:
    """Stream crypto prices from Binance WebSocket with REST fallback."""
    log.info("Crypto streamer started")
    failures = 0
    while True:
        try:
            active  = engine.get_active_assets()
            streams = [
                f"{sym}@miniTicker"
                for name, sym in cfg.BINANCE_SYMBOLS.items()
                if name in active
            ]
            if not streams:
                await asyncio.sleep(10)
                continue

            url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                log.info("Binance WebSocket connected ✓ (%d streams)", len(streams))
                failures = 0
                async for raw_msg in ws:
                    try:
                        msg  = json.loads(raw_msg)
                        data = msg.get("data", {})
                        name = cfg.BINANCE_SYMBOL_TO_NAME.get(data.get("s", "").lower())
                        if name and "c" in data:
                            price = float(data["c"])
                            engine.on_price_update(name, price)
                            _on_price_update(name, price)
                    except (json.JSONDecodeError, ValueError, KeyError):
                        pass
        except Exception as exc:
            failures += 1
            backoff = min(cfg.CRYPTO_WS_RECONNECT_DELAY * failures, 60)
            log.warning("Crypto streamer error (attempt %d): %s — retry in %ds", failures, exc, backoff)
            await asyncio.sleep(backoff)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
