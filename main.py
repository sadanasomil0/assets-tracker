"""
main.py — Entry point for the Multi-Asset Price Alert Bot.

Orchestrates four concurrent async tasks:
    1. Stock/commodity poller (yfinance)
    2. Crypto WebSocket stream (Binance)
    3. Telegram bot (commands + notifications)
    4. Alert dispatcher (queue → Telegram sender)

Usage:
    python main.py            # normal mode
    python main.py --dry-run  # no Telegram sends, console alerts only
"""

import argparse
import asyncio
import signal
import sys

import config
import persistence
from alert_engine import AlertEngine, AlertEvent
from fetchers.crypto_fetcher import stream_crypto
from fetchers.stock_fetcher import poll_stocks
from logger import get_logger
from telegram_bot import TelegramBot
from discord_notifier import send_alert as discord_send_alert

log = get_logger("main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Asset Price Alert Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending Telegram messages (prints alerts to console)",
    )
    parser.add_argument(
        "--no-restore",
        action="store_true",
        help="Skip restoring saved state on startup (use default ranges only)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    log.info("=" * 50)
    log.info("  Multi-Asset Price Alert Bot")
    log.info("  Mode: %s", "DRY-RUN" if args.dry_run else "LIVE")
    log.info("=" * 50)

    # ── Validate config ──────────────────────────────────────────────────
    if not args.dry_run:
        if not config.TELEGRAM_BOT_TOKEN:
            log.error("TELEGRAM_BOT_TOKEN not set. See .env.example")
            sys.exit(1)
        if not config.TELEGRAM_CHAT_ID:
            log.warning("TELEGRAM_CHAT_ID not set — alerts won't be sent until configured")

    # ── Initialise alert queue & engine ─────────────────────────────────
    alert_queue: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=500)

    def on_alert(event: AlertEvent) -> None:
        """Thread-safe callback: push alert events into the async queue."""
        try:
            alert_queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("Alert queue full, dropping alert for %s", event.asset_name)

    engine = AlertEngine(on_alert=on_alert)
    bot    = TelegramBot(alert_engine=engine, dry_run=args.dry_run)

    # ── Load state: try persistence file first, then fall back to defaults ─
    if not args.no_restore:
        restored = persistence.load_state(engine)
        if restored == 0:
            # Nothing restored — load built-in defaults
            for name, (min_p, max_p) in config.DEFAULT_RANGES.items():
                engine.add_asset(name, min_p, max_p)
            log.info("Loaded %d default price ranges", len(config.DEFAULT_RANGES))
    else:
        for name, (min_p, max_p) in config.DEFAULT_RANGES.items():
            engine.add_asset(name, min_p, max_p)
        log.info("--no-restore: loaded %d default price ranges", len(config.DEFAULT_RANGES))

    # ── Build Telegram application ───────────────────────────────────────
    app = bot.build_app() if not args.dry_run else None

    # ── Alert dispatcher ─────────────────────────────────────────────────
    async def dispatch_alerts() -> None:
        """Consume alert events from the queue and send Discord notifications."""
        while True:
            event = await alert_queue.get()
            try:
                # Determine condition and target
                if event.price >= event.max_price:
                    condition = "reached or exceeded upper target"
                    target = event.max_price
                elif event.price <= event.min_price:
                    condition = "dropped to or below lower target"
                    target = event.min_price
                else:
                    condition = "entered range"
                    target = event.min_price  # default to lower bound
                
                # Send to Discord
                discord_send_alert(
                    asset=event.asset_name,
                    price=event.price,
                    condition=condition,
                    target=target
                )
                # Also try Telegram (will fail gracefully if not configured)
                await bot.send_alert(event)
            except Exception as exc:
                log.error("Failed to dispatch alert: %s", exc)
            finally:
                alert_queue.task_done()

    # ── Graceful shutdown ────────────────────────────────────────────────
    shutdown_event = asyncio.Event()

    def _signal_handler(sig, frame):
        log.info("Shutdown signal received (%s), stopping…", sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    # ── Launch all tasks ─────────────────────────────────────────────────
    log.info("Starting all subsystems…")

    tasks = [
        asyncio.create_task(
            poll_stocks(engine.on_price_update, engine.get_tracked_assets),
            name="stock_poller",
        ),
        asyncio.create_task(
            stream_crypto(engine.on_price_update, engine.get_tracked_assets),
            name="crypto_streamer",
        ),
        asyncio.create_task(dispatch_alerts(), name="alert_dispatcher"),
    ]

    if app:
        async def run_telegram():
            """Run the Telegram updater alongside our tasks."""
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            log.info("Telegram bot started ✓")
            await shutdown_event.wait()
            log.info("Stopping Telegram bot…")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

        tasks.append(asyncio.create_task(run_telegram(), name="telegram_bot"))
    else:
        log.info("[DRY-RUN] Telegram bot not started")

    # ── Wait for shutdown ────────────────────────────────────────────────
    try:
        if app:
            await shutdown_event.wait()
        else:
            await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        log.info("Saving state before shutdown…")
        persistence.save_state(engine)

        log.info("Cancelling tasks…")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("Bot stopped. Goodbye! 👋")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
