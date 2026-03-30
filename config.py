"""
config.py — Central configuration for the Price Alert Bot.

Contains ticker mappings, default price ranges, polling intervals,
and asset categorisation.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Polling / streaming intervals (seconds) ────────────────────────────────
STOCK_POLL_INTERVAL: int = 15          # yfinance polling for stocks & commodities
CRYPTO_WS_RECONNECT_DELAY: int = 5    # seconds before reconnecting WebSocket
CRYPTO_REST_FALLBACK_INTERVAL: int = 10  # REST fallback poll interval

# ─── Alert behaviour ─────────────────────────────────────────────────────────
# Minimum seconds between consecutive alerts for the same asset.
# Prevents spam when price oscillates rapidly at a range boundary.
ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))  # 5 minutes

# Maximum number of alert events kept in memory for /alerts history.
ALERT_HISTORY_MAX: int = 100

# ─── Persistence ─────────────────────────────────────────────────────────────
# JSON file used to save/restore tracked asset ranges across restarts.
PERSISTENCE_FILE: str = os.getenv("PERSISTENCE_FILE", "state.json")

# ─── Asset categories ────────────────────────────────────────────────────────
# Maps a user-friendly name → yfinance ticker
YFINANCE_TICKERS: dict[str, str] = {
    # Commodities
    "GOLD":      "GC=F",
    "SILVER":    "SI=F",
    "CRUDE_OIL": "CL=F",
    # Stocks
    "NVIDIA":    "NVDA",
    "TESLA":     "TSLA",
    "GOOGLE":    "GOOGL",
    "AMAZON":    "AMZN",
    "ORACLE":    "ORCL",
    "APPLE":     "AAPL",
    "MICROSOFT": "MSFT",
    "META":      "META",
    # Indices
    "SP500":     "^GSPC",
    "NASDAQ":    "^IXIC",
    "DOW":       "^DJI",
}

# Maps a user-friendly name → Binance WebSocket stream symbol
BINANCE_SYMBOLS: dict[str, str] = {
    "BTC":  "btcusdt",
    "ETH":  "ethusdt",
    "XRP":  "xrpusdt",
    "SOL":  "solusdt",
    "BNB":  "bnbusdt",
    "DOGE": "dogeusdt",
    "ADA":  "adausdt",
    "MATIC":"maticusdt",
}

# Reverse lookup: Binance stream symbol → user-friendly name
BINANCE_SYMBOL_TO_NAME: dict[str, str] = {v: k for k, v in BINANCE_SYMBOLS.items()}

# All supported asset names (for validation)
ALL_ASSETS: set[str] = set(YFINANCE_TICKERS.keys()) | set(BINANCE_SYMBOLS.keys())

# ─── Default price ranges (min, max) — updated to current market levels ─────
DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    # Commodities
    "GOLD":      (2900.0, 3200.0),
    "SILVER":    (30.0,   36.0),
    "CRUDE_OIL": (65.0,   75.0),
    # Crypto
    "BTC":       (80000.0, 95000.0),
    "ETH":       (1700.0,  2200.0),
    "XRP":       (2.00,    2.80),
    "SOL":       (120.0,   175.0),
    "BNB":       (580.0,   650.0),
    "DOGE":      (0.15,    0.25),
    "ADA":       (0.65,    0.90),
    "MATIC":     (0.40,    0.65),
    # Stocks
    "NVIDIA":    (100.0,  135.0),
    "TESLA":     (240.0,  310.0),
    "GOOGLE":    (155.0,  185.0),
    "AMAZON":    (195.0,  225.0),
    "ORACLE":    (155.0,  185.0),
    "APPLE":     (200.0,  240.0),
    "MICROSOFT": (370.0,  420.0),
    "META":      (520.0,  620.0),
    # Indices
    "SP500":     (5400.0, 5800.0),
    "NASDAQ":    (17000.0,19000.0),
    "DOW":       (41000.0,44000.0),
}

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_FILE: str = "bot.log"
LOG_MAX_BYTES: int = 5 * 1024 * 1024   # 5 MB
LOG_BACKUP_COUNT: int = 3
