"""
stock_fetcher.py — Polls yfinance for live prices of stocks, indices,
and commodities on a configurable interval.

Feeds price updates into the alert engine callback.
"""

import asyncio
from typing import Callable

import yfinance as yf

import config
from logger import get_logger

log = get_logger("stock_fetcher")


async def poll_stocks(
    on_price: Callable[[str, float], None],
    get_active_assets: Callable[[], dict[str, tuple[float, float]]],
) -> None:
    """
    Continuously poll yfinance for prices of stocks/commodities/indices.

    Args:
        on_price: callback(asset_name, price) invoked for every price update.
        get_active_assets: returns the current dict of tracked asset ranges so
                          we only fetch tickers the user cares about.
    """
    log.info("Stock/commodity poller started (interval=%ds)", config.STOCK_POLL_INTERVAL)
    consecutive_failures = 0
    max_backoff = 120  # seconds

    while True:
        try:
            # Build a list of yfinance tickers we need to fetch
            active = get_active_assets()
            tickers_to_fetch: dict[str, str] = {}  # name → yf_ticker
            for name, yf_ticker in config.YFINANCE_TICKERS.items():
                if name in active:
                    tickers_to_fetch[name] = yf_ticker

            if not tickers_to_fetch:
                log.debug("No active yfinance assets to poll, sleeping…")
                await asyncio.sleep(config.STOCK_POLL_INTERVAL)
                continue

            # Fetch all tickers in one batch call (efficient)
            log.debug("Fetching yfinance tickers: %s", " ".join(tickers_to_fetch.values()))

            data = await asyncio.to_thread(
                _fetch_batch, list(tickers_to_fetch.values())
            )

            # Map results back to friendly names
            yf_to_name = {v: k for k, v in tickers_to_fetch.items()}
            for yf_ticker, price in data.items():
                name = yf_to_name.get(yf_ticker)
                if name and price is not None:
                    log.debug("  %s (%s) = $%.4f", name, yf_ticker, price)
                    on_price(name, price)

            consecutive_failures = 0  # reset on success

        except Exception as exc:
            consecutive_failures += 1
            backoff = min(config.STOCK_POLL_INTERVAL * (2 ** consecutive_failures), max_backoff)
            log.warning(
                "yfinance poll failed (attempt %d): %s — retrying in %ds",
                consecutive_failures, exc, backoff,
            )
            await asyncio.sleep(backoff)
            continue

        await asyncio.sleep(config.STOCK_POLL_INTERVAL)


def _fetch_batch(tickers: list[str]) -> dict[str, float | None]:
    """
    Synchronous helper — fetches the latest price for a batch of yfinance
    tickers. Returns {ticker: price}.

    Strategy:
        1. Try fast_info.last_price for each ticker (fastest, works outside market hours)
        2. Fall back to batch download with 5d period if fast_info fails
    """
    results: dict[str, float | None] = {}

    # Strategy 1: fast_info (works even on weekends/after-hours)
    remaining = []
    for ticker_str in tickers:
        try:
            ticker = yf.Ticker(ticker_str)
            # fast_info is an object, not a dict — access as attribute with fallback
            fi = ticker.fast_info
            price = None
            try:
                price = fi.last_price
            except AttributeError:
                pass
            if price is None:
                try:
                    price = fi.lastPrice
                except AttributeError:
                    pass
            if price and float(price) > 0:
                results[ticker_str] = float(price)
            else:
                remaining.append(ticker_str)
        except Exception as exc:
            log.debug("fast_info failed for %s: %s", ticker_str, exc)
            remaining.append(ticker_str)

    if not remaining:
        return results

    # Strategy 2: batch download with 5d period (wider window for weekends)
    try:
        data = yf.download(
            tickers=remaining,
            period="5d",
            interval="1d",
            progress=False,
            threads=True,
            auto_adjust=True,
        )
        if data.empty:
            log.debug("yfinance batch download returned empty (market may be closed)")
            return results

        if len(remaining) == 1:
            ticker = remaining[0]
            if "Close" in data.columns:
                last_price = data["Close"].dropna().iloc[-1]
                results[ticker] = float(last_price)
        else:
            for ticker in remaining:
                try:
                    close_col = data["Close"]
                    if ticker in close_col.columns:
                        series = close_col[ticker].dropna()
                        if not series.empty:
                            results[ticker] = float(series.iloc[-1])
                except (KeyError, IndexError) as e:
                    log.debug("Could not get price for %s: %s", ticker, e)

    except Exception as exc:
        log.error("yfinance batch download error: %s", exc)

    return results
