"""
telegram_bot.py — Telegram integration for notifications and user commands.

Sends formatted alert messages and handles interactive commands:
    /add    <ASSET> <MIN> <MAX>  — set a price range alert
    /remove <ASSET>              — stop tracking an asset
    /list                        — show all tracked assets
    /price  <ASSET>              — get last known price for an asset
    /alerts                      — show last 10 triggered alerts
    /pause                       — silence all alert notifications
    /resume                      — re-enable alert notifications
    /status                      — bot health check
    /help                        — this message
"""

import asyncio
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import config
from alert_engine import AlertEngine, AlertEvent
from logger import get_logger

log = get_logger("telegram_bot")

# Rate-limit: minimum seconds between Telegram messages
_MIN_SEND_INTERVAL = 1.0
_last_send_time: float = 0.0

# ── Markdown V2 escape helper ─────────────────────────────────────────────────
_MD2_SPECIAL = r"\_*[]()~`>#+-=|{}.!"

def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in _MD2_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text


class TelegramBot:
    """Wraps python-telegram-bot to provide both commands and alert sending."""

    def __init__(self, alert_engine: AlertEngine, dry_run: bool = False) -> None:
        self.engine = alert_engine
        self.dry_run = dry_run
        self._app: Application | None = None
        self._start_time = datetime.now(timezone.utc)

    # ── Initialise the bot application ───────────────────────────────────

    def build_app(self) -> Application:
        """Create and configure the Telegram Application."""
        if not config.TELEGRAM_BOT_TOKEN:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not set. "
                "Add it to your .env file (see .env.example)."
            )

        builder = Application.builder().token(config.TELEGRAM_BOT_TOKEN)
        self._app = builder.build()

        # Register command handlers
        self._app.add_handler(CommandHandler("start",  self._cmd_help))
        self._app.add_handler(CommandHandler("help",   self._cmd_help))
        self._app.add_handler(CommandHandler("add",    self._cmd_add))
        self._app.add_handler(CommandHandler("remove", self._cmd_remove))
        self._app.add_handler(CommandHandler("list",   self._cmd_list))
        self._app.add_handler(CommandHandler("price",  self._cmd_price))
        self._app.add_handler(CommandHandler("alerts", self._cmd_alerts))
        self._app.add_handler(CommandHandler("pause",  self._cmd_pause))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("status", self._cmd_status))

        return self._app

    # ── Send alert notification ──────────────────────────────────────────

    async def send_alert(self, event: AlertEvent) -> None:
        """Send a price-alert message to the configured Telegram chat."""
        asset  = _esc(event.asset_name)
        price  = _esc(f"${event.price:,.4f}")
        rng    = _esc(f"${event.min_price:,.4f} – ${event.max_price:,.4f}")
        ts     = _esc(event.timestamp.strftime("%Y-%m-%d %H:%M:%S"))

        text = (
            f"🔔 *Price Alert — {asset}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Current Price:* `{price}`\n"
            f"📊 *Target Range:* `{rng}`\n"
            f"🕐 *Time \\(UTC\\):* `{ts}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"_Price has entered your defined range\\!_"
        )

        if self.dry_run:
            log.info("[DRY-RUN] Would send alert:\n%s", text)
            return

        await self._send_message(text)

    async def _send_message(self, text: str, chat_id: str | None = None) -> None:
        """Send a MarkdownV2 message with simple rate-limiting."""
        global _last_send_time

        target_chat = chat_id or config.TELEGRAM_CHAT_ID
        if not target_chat:
            log.warning("No TELEGRAM_CHAT_ID configured, skipping message send")
            return

        # Simple rate limiting using running loop time
        loop = asyncio.get_running_loop()
        now = loop.time()
        elapsed = now - _last_send_time
        if elapsed < _MIN_SEND_INTERVAL:
            await asyncio.sleep(_MIN_SEND_INTERVAL - elapsed)

        try:
            if self._app and self._app.bot:
                await self._app.bot.send_message(
                    chat_id=target_chat,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                _last_send_time = asyncio.get_running_loop().time()
                log.debug("Telegram message sent to chat %s", target_chat)
        except Exception as exc:
            log.error("Failed to send Telegram message: %s", exc)

    # ── Command handlers ─────────────────────────────────────────────────

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help and /start."""
        commodities = sorted(k for k in config.YFINANCE_TICKERS if k in ("GOLD","SILVER","CRUDE_OIL"))
        stocks      = sorted(k for k in config.YFINANCE_TICKERS if k not in commodities)
        crypto      = sorted(config.BINANCE_SYMBOLS.keys())

        text = (
            "📈 *Multi\\-Asset Price Alert Bot*\n\n"
            "*Commands:*\n"
            "`/add <ASSET> <MIN> <MAX>` — Track an asset\n"
            "`/remove <ASSET>` — Stop tracking\n"
            "`/list` — Show all tracked assets\n"
            "`/price <ASSET>` — Get current price\n"
            "`/alerts` — Last 10 triggered alerts\n"
            "`/pause` — Mute all notifications\n"
            "`/resume` — Unmute notifications\n"
            "`/status` — Bot health check\n"
            "`/help` — This message\n\n"
            f"*📦 Commodities:* `{', '.join(commodities)}`\n"
            f"*₿ Crypto:* `{', '.join(crypto)}`\n"
            f"*📊 Stocks/Indices:* `{', '.join(stocks)}`\n\n"
            "_Example:_ `/add BTC 80000 90000`"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

    async def _cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /add <ASSET> <MIN> <MAX>."""
        args = context.args
        if not args or len(args) != 3:
            await update.message.reply_text(
                "⚠️ Usage: `/add <ASSET> <MIN_PRICE> <MAX_PRICE>`\n"
                "Example: `/add BTC 80000 90000`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        asset_name = args[0].upper()
        try:
            min_price = float(args[1])
            max_price = float(args[2])
        except ValueError:
            await update.message.reply_text("⚠️ MIN and MAX must be numbers\\.")
            return

        if min_price >= max_price:
            await update.message.reply_text("⚠️ MIN must be less than MAX\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return

        if asset_name not in config.ALL_ASSETS:
            supported = _esc(", ".join(sorted(config.ALL_ASSETS)))
            await update.message.reply_text(
                f"⚠️ Unknown asset `{_esc(asset_name)}`\\.\n\nSupported: `{supported}`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        self.engine.add_asset(asset_name, min_price, max_price)
        min_str = _esc(f"${min_price:,.4f}")
        max_str = _esc(f"${max_price:,.4f}")
        await update.message.reply_text(
            f"✅ Tracking *{_esc(asset_name)}*\n"
            f"Range: `{min_str}` \u2013 `{max_str}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /remove <ASSET>."""
        args = context.args
        if not args or len(args) != 1:
            await update.message.reply_text("⚠️ Usage: `/remove <ASSET>`", parse_mode=ParseMode.MARKDOWN_V2)
            return

        asset_name = args[0].upper()
        if self.engine.remove_asset(asset_name):
            await update.message.reply_text(
                f"🗑️ Stopped tracking *{_esc(asset_name)}*\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                f"⚠️ `{_esc(asset_name)}` is not being tracked\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /list — show all tracked assets."""
        details = self.engine.get_asset_details()
        if not details:
            await update.message.reply_text(
                "📭 No assets tracked\\. Use `/add` to start\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        lines = ["📋 *Tracked Assets:*\n"]
        for d in sorted(details, key=lambda x: x["name"]):
            state_emoji = "🟢" if d["state"] == "INSIDE" else "⚪"
            pause_tag   = " ⏸" if d.get("paused") else ""
            price_str   = _esc(f"${d['last_price']:,.4f}") if d["last_price"] else "N/A"
            rng_min     = _esc(f"${d['min']:,.4f}")
            rng_max     = _esc(f"${d['max']:,.4f}")
            lines.append(
                f"{state_emoji} *{_esc(d['name'])}*{_esc(pause_tag)}\n"
                f"   Range: `{rng_min}` \u2013 `{rng_max}`\n"
                f"   Last: `{price_str}` \\| State: `{_esc(d['state'])}`"
            )

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)

    async def _cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /price <ASSET> — show last known price."""
        args = context.args
        if not args or len(args) != 1:
            await update.message.reply_text(
                "⚠️ Usage: `/price <ASSET>`\nExample: `/price BTC`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        asset_name = args[0].upper()
        price = self.engine.get_asset_price(asset_name)

        if price is None:
            await update.message.reply_text(
                f"❓ No price data for `{_esc(asset_name)}` yet\\.\n"
                "_Make sure it's tracked with_ `/add`\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                f"💰 *{_esc(asset_name)}* latest price: `{_esc(f'${price:,.4f}')}`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _cmd_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /alerts — show last 10 triggered alerts."""
        history = self.engine.get_alert_history(limit=10)
        if not history:
            await update.message.reply_text(
                "📭 No alerts have been triggered yet\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        lines = ["🔔 *Recent Alerts \\(newest first\\):*\n"]
        for event in history:
            ts   = _esc(event.timestamp.strftime("%m/%d %H:%M UTC"))
            name = _esc(event.asset_name)
            px   = _esc(f"${event.price:,.4f}")
            lines.append(f"• *{name}* — `{px}` at {ts}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /pause — silence all alert notifications."""
        self.engine.pause_all()
        await update.message.reply_text(
            "⏸️ *Alerts paused\\.* You won't receive notifications until you send `/resume`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resume — re-enable alert notifications."""
        self.engine.resume_all()
        await update.message.reply_text(
            "▶️ *Alerts resumed\\.* You will now receive notifications again\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status — bot health check."""
        now = datetime.now(timezone.utc)
        uptime = now - self._start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        tracked     = self.engine.get_tracked_assets()
        crypto_cnt  = sum(1 for n in tracked if n in config.BINANCE_SYMBOLS)
        stock_cnt   = len(tracked) - crypto_cnt
        paused_flag = "⏸️ YES" if self.engine.is_paused() else "▶️ NO"
        alert_cnt   = len(self.engine.get_alert_history(limit=config.ALERT_HISTORY_MAX))

        text = (
            "🤖 *Bot Status*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ Uptime: `{_esc(f'{hours}h {minutes}m {seconds}s')}`\n"
            f"📊 Tracking: `{len(tracked)}` assets "
            f"\\(`{crypto_cnt}` crypto, `{stock_cnt}` stocks/commodities\\)\n"
            f"🔔 Alerts fired: `{alert_cnt}`\n"
            f"⏸️ Paused: {_esc(paused_flag)}\n"
            f"🔄 Stock poll: `{config.STOCK_POLL_INTERVAL}s`\n"
            f"⏳ Cooldown: `{config.ALERT_COOLDOWN_SECONDS}s`\n"
            f"📡 Crypto: WebSocket streaming\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
