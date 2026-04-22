---
title: Assets Tracker API
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.31.0
app_file: app.py
pinned: false
---
# Multi-Asset Real-Time Price Alert Bot 📈🔔

A production-ready Python bot that monitors **commodities**, **cryptocurrencies**, and **stocks** in real-time, and sends instant **Telegram alerts** when prices enter your defined ranges.

## ✨ Features

| Feature | Details |
|---|---|
| **Multi-asset tracking** | Gold, Silver, Crude Oil, BTC, ETH, XRP, SOL, NVIDIA, Tesla, Google, Amazon, Oracle, S&P 500 |
| **Real-time crypto** | Binance WebSocket streaming with REST fallback |
| **Smart polling** | yfinance batch polling every 15s for stocks/commodities |
| **Dedup alerts** | State-machine logic — alerts only on range entry, resets on exit |
| **Telegram commands** | `/add`, `/remove`, `/list`, `/status`, `/help` |
| **Dry-run mode** | Test without Telegram via `--dry-run` |
| **Error handling** | Exponential backoff, auto-reconnect, structured logging |

## 📁 Project Structure

```
photonic-perigee/
├── main.py                  # Entry point & orchestrator
├── config.py                # Configuration & environment
├── alert_engine.py          # State-machine alert logic
├── telegram_bot.py          # Telegram commands & notifications
├── logger.py                # Rotating log setup
├── fetchers/
│   ├── __init__.py
│   ├── stock_fetcher.py     # yfinance polling
│   └── crypto_fetcher.py    # Binance WebSocket + REST
├── tests/
│   └── test_alert_engine.py # Unit tests
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.10+** installed
- A **Telegram account**

### 2. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. You'll receive a **Bot Token** like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
4. **Get your Chat ID:**
   - Search for **@userinfobot** on Telegram
   - Send `/start` — it will reply with your Chat ID
   - Alternatively, send a message to your bot, then visit:
     ```
     https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
     ```
     Look for `"chat":{"id": YOUR_CHAT_ID}`

### 3. Install & Configure

```bash
# Clone / navigate to the project
cd photonic-perigee

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux

# Edit .env with your Telegram credentials
notepad .env
```

Fill in your `.env`:
```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
```

### 4. Run the Bot

```bash
# Live mode (sends Telegram alerts)
python main.py

# Dry-run mode (console alerts only, no Telegram needed)
python main.py --dry-run
```

### 5. Run Tests

```bash
python -m pytest tests/ -v
```

## 💬 Telegram Commands

| Command | Description | Example |
|---|---|---|
| `/add <ASSET> <MIN> <MAX>` | Start tracking an asset | `/add BTC 60000 62000` |
| `/remove <ASSET>` | Stop tracking an asset | `/remove BTC` |
| `/list` | Show all tracked assets | `/list` |
| `/status` | Bot health check & uptime | `/status` |
| `/help` | Show all commands | `/help` |

### Supported Asset Names

| Category | Assets |
|---|---|
| Commodities | `GOLD`, `SILVER`, `CRUDE_OIL` |
| Crypto | `BTC`, `ETH`, `XRP`, `SOL` |
| Stocks | `NVIDIA`, `TESLA`, `GOOGLE`, `AMAZON`, `ORACLE` |
| Indices | `SP500` |

## 🔔 How Alerts Work

The bot uses a **state machine** to avoid duplicate alerts:

```
Price OUTSIDE range → enters range → 🔔 ALERT sent
Price INSIDE range  → stays inside  → no alert (dedup)
Price INSIDE range  → exits range   → state resets
Price OUTSIDE range → re-enters     → 🔔 ALERT sent again
```

### Sample Alert Message

```
🔔 Price Alert — BTC
━━━━━━━━━━━━━━━━━━━━━━━
💰 Current Price: $61,234.5600
📊 Target Range: $60,000.0000 – $62,000.0000
🕐 Time (UTC): 2026-03-22 06:15:30
━━━━━━━━━━━━━━━━━━━━━━━
Price has entered your defined range!
```

## ⚙️ Configuration

Edit `config.py` to customise:

| Setting | Default | Description |
|---|---|---|
| `STOCK_POLL_INTERVAL` | `15` | Seconds between yfinance polls |
| `CRYPTO_WS_RECONNECT_DELAY` | `5` | Seconds before WebSocket reconnect |
| `DEFAULT_RANGES` | See file | Pre-loaded price ranges |

## ☁️ Deployment

### Option A: Run on a VPS (e.g., DigitalOcean, AWS EC2)

```bash
# SSH into your server
ssh user@your-server

# Clone the project, install dependencies
git clone <your-repo-url>
cd photonic-perigee
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure .env
nano .env

# Run with nohup (persists after disconnecting)
nohup python main.py > output.log 2>&1 &

# Or use systemd for auto-restart (create /etc/systemd/system/pricealert.service):
```

**systemd service file** (`/etc/systemd/system/pricealert.service`):
```ini
[Unit]
Description=Price Alert Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/photonic-perigee
ExecStart=/home/ubuntu/photonic-perigee/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/photonic-perigee/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pricealert
sudo systemctl start pricealert
sudo systemctl status pricealert
```

### Option B: Run on Replit

1. Create a new **Python** Repl
2. Upload all project files
3. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Replit's **Secrets** tab
4. Set the run command to `python main.py`
5. Click **Run** — the bot will stay alive as long as the Repl is active
6. Use Replit's **Always On** feature (paid) for 24/7 uptime

## 📝 Logging

- **Console**: INFO level and above
- **File** (`bot.log`): DEBUG level, rotating at 5MB with 3 backups
- Log format: `2026-03-22 06:15:30 | INFO     | main | Bot started`

## 🛡️ Error Handling

| Scenario | Behaviour |
|---|---|
| yfinance API failure | Exponential backoff (max 120s) |
| Binance WebSocket disconnect | Auto-reconnect with backoff (5 attempts) |
| WebSocket fails repeatedly | Falls back to REST API polling |
| Telegram send failure | Logged, retried on next alert |
| Invalid command input | User-friendly error message |

## License

MIT
