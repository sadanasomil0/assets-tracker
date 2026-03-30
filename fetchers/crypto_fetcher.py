"""
crypto_fetcher.py — Real-time crypto prices via Binance WebSocket,
with REST API fallback.

Subscribes to Binance combined ticker streams for all active crypto assets.
"""

import asyncio
import json
from typing import Callable

import aiohttp
import websockets
import websockets.exceptions

import config
from logger import get_logger

log = get_logger("crypto_fetcher")

BINANCE_WS_BASE  = "wss://stream.binance.com:9443/ws"
BINANCE_REST_URL = "https://api.binance.com/api/v3/ticker/price"


async def stream_crypto(
    on_price: Callable[[str, float], None],
    get_active_assets: Callable[[], dict[str, tuple[float, float]]],
) -> None:
    """
    Connect to Binance WebSocket for real-time crypto prices.
    Falls back to REST polling if WebSocket connection fails repeatedly.
    """
    consecutive_ws_failures = 0
    max_ws_retries = 5

    while True:
        try:
            await _run_websocket(on_price, get_active_assets)
            consecutive_ws_failures = 0  # reset on clean exit
        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.InvalidURI,
            websockets.exceptions.InvalidHandshake,
            OSError,
            ConnectionRefusedError,
        ) as exc:
            consecutive_ws_failures += 1
            log.warning(
                "Binance WebSocket disconnected (attempt %d/%d): %s",
                consecutive_ws_failures, max_ws_retries, exc,
            )

            if consecutive_ws_failures >= max_ws_retries:
                log.warning("WebSocket failed %d times, switching to REST fallback", max_ws_retries)
                await _rest_fallback(on_price, get_active_assets)
                consecutive_ws_failures = 0  # reset after fallback session
            else:
                backoff = config.CRYPTO_WS_RECONNECT_DELAY * consecutive_ws_failures
                log.info("Reconnecting WebSocket in %ds…", backoff)
                await asyncio.sleep(backoff)

        except Exception as exc:
            log.error("Unexpected crypto fetcher error: %s", exc, exc_info=True)
            await asyncio.sleep(config.CRYPTO_WS_RECONNECT_DELAY)


async def _run_websocket(
    on_price: Callable[[str, float], None],
    get_active_assets: Callable[[], dict[str, tuple[float, float]]],
) -> None:
    """Subscribe to Binance combined mini-ticker streams for active crypto assets."""
    active = get_active_assets()
    streams = [
        f"{symbol}@miniTicker"
        for name, symbol in config.BINANCE_SYMBOLS.items()
        if name in active
    ]

    if not streams:
        log.debug("No active crypto assets, sleeping…")
        await asyncio.sleep(config.CRYPTO_REST_FALLBACK_INTERVAL)
        return

    stream_path = "/".join(streams)
    url = f"wss://stream.binance.com:9443/stream?streams={stream_path}"
    log.info("Connecting to Binance WebSocket: %d stream(s)", len(streams))

    async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
        log.info("Binance WebSocket connected ✓")
        async for raw_msg in ws:
            try:
                msg  = json.loads(raw_msg)
                data = msg.get("data", {})
                # 's' field is the raw symbol e.g. "BTCUSDT"
                raw_lower = data.get("s", "").lower()  # e.g. "btcusdt"
                name = config.BINANCE_SYMBOL_TO_NAME.get(raw_lower)

                if name and "c" in data:
                    price = float(data["c"])  # 'c' = close price
                    log.debug("  WS %s = $%.4f", name, price)
                    on_price(name, price)

            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                log.debug("Skipping malformed WS message: %s", exc)


async def _rest_fallback(
    on_price: Callable[[str, float], None],
    get_active_assets: Callable[[], dict[str, tuple[float, float]]],
) -> None:
    """Poll Binance REST API as fallback when WebSocket is unavailable."""
    log.info("Running Binance REST fallback poller (interval=%ds)", config.CRYPTO_REST_FALLBACK_INTERVAL)

    # Run for a limited period then let the outer loop retry WebSocket (~5 minutes)
    for _ in range(30):
        try:
            active = get_active_assets()
            async with aiohttp.ClientSession() as session:
                for name, symbol in config.BINANCE_SYMBOLS.items():
                    if name not in active:
                        continue
                    api_symbol = symbol.upper()  # e.g. BTCUSDT
                    url = f"{BINANCE_REST_URL}?symbol={api_symbol}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data  = await resp.json()
                            price = float(data["price"])
                            log.debug("  REST %s = $%.4f", name, price)
                            on_price(name, price)
                        else:
                            log.warning("Binance REST %s returned HTTP %d", api_symbol, resp.status)
        except Exception as exc:
            log.warning("Binance REST fallback error: %s", exc)

        await asyncio.sleep(config.CRYPTO_REST_FALLBACK_INTERVAL)
