# 🚀 Deploy Your Price Alert Bot to Free Cloud Servers

This guide shows you how to deploy your Multi-Asset Price Alert Bot to free cloud platforms so it runs 24/7 and sends you Telegram alerts whenever prices enter your defined ranges.

## Prerequisites

Before deploying, you need:

1. **Telegram Bot Token** - Get from [@BotFather](https://t.me/BotFather)
2. **Telegram Chat ID** - Get from [@userinfobot](https://t.me/userinfobot)
3. **GitHub Account** - To store your code

---

## Option 1: Render (Recommended - Easiest)

Render offers a free tier that's perfect for this bot.

### Step 1: Push Code to GitHub

```bash
cd /workspace
git init
git add .
git commit -m "Initial commit"
# Create a new repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/price-alert-bot.git
git push -u origin main
```

### Step 2: Deploy to Render

1. Go to [render.com](https://render.com) and sign up
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `price-alert-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: **Free**
5. Click **"Advanced"** and add environment variables:
   - `TELEGRAM_BOT_TOKEN`: Your bot token
   - `TELEGRAM_CHAT_ID`: Your chat ID
6. Click **"Create Web Service"**

### Step 3: Verify Deployment

- Check the logs in Render dashboard
- Send `/status` to your bot on Telegram
- Add alerts with `/add BTC 60000 62000`

**Note**: Free instances sleep after 15 minutes of inactivity. To keep it awake:
- Use a free uptime monitor like [UptimeRobot](https://uptimerobot.com) to ping your service every 5 minutes
- Or upgrade to a paid plan ($7/month)

---

## Option 2: Railway

Railway offers a free trial with generous resources.

### Step 1: Deploy

1. Go to [railway.app](https://railway.app)
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository
4. Railway auto-detects Python and creates a `Procfile`

### Step 2: Create Procfile

Create a file named `Procfile` (no extension):

```
worker: python main.py
```

### Step 3: Add Environment Variables

In Railway dashboard:
- Go to **Variables** tab
- Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

### Step 4: Deploy

Railway will automatically deploy. Check logs to verify.

---

## Option 3: Oracle Cloud Free Tier (Most Powerful - Always On)

Oracle offers always-free VMs with no sleep.

### Step 1: Create Account

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com)
2. Navigate to **Compute** → **Instances**
3. Click **"Create Instance"**

### Step 2: Configure VM

- **Image**: Ubuntu 22.04
- **Shape**: VM.Standard.A1.Flex (free tier)
- **SSH Keys**: Generate or upload your key

### Step 3: Connect and Deploy

```bash
# SSH into your VM
ssh -i your_key.pem ubuntu@YOUR_VM_IP

# Install Python and git
sudo apt update
sudo apt install -y python3 python3-pip git

# Clone your repo
git clone https://github.com/YOUR_USERNAME/price-alert-bot.git
cd price-alert-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
nano .env
# Add your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
```

### Step 4: Run as Systemd Service

Create service file:

```bash
sudo nano /etc/systemd/system/pricealert.service
```

Paste this content:

```ini
[Unit]
Description=Price Alert Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/price-alert-bot
ExecStart=/home/ubuntu/price-alert-bot/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/price-alert-bot/.env

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pricealert
sudo systemctl start pricealert
sudo systemctl status pricealert
```

---

## Option 4: Hugging Face Spaces (Simple Alternative)

Hugging Face Spaces can run Python apps for free.

### Step 1: Create Space

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces)
2. Click **"Create new Space"**
3. Choose **Docker** as SDK
4. Make it public or private

### Step 2: Add Dockerfile

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### Step 3: Add Secrets

In Space Settings → **Repository secrets**:
- Add `TELEGRAM_BOT_TOKEN`
- Add `TELEGRAM_CHAT_ID`

### Step 4: Deploy

Push your code to the Space repository. It will auto-deploy.

---

## Testing Your Deployment

Once deployed, test these commands on Telegram:

1. **Check status**: `/status`
2. **Add alert**: `/add BTC 60000 62000`
3. **List alerts**: `/list`
4. **Remove alert**: `/remove BTC`

### Sample Alert Message

When BTC enters your range, you'll receive:

```
🔔 Price Alert — BTC
━━━━━━━━━━━━━━━━━━━━━━━
💰 Current Price: $61,234.56
📊 Target Range: $60,000.00 – $62,000.00
🕐 Time (UTC): 2026-03-22 06:15:30
━━━━━━━━━━━━━━━━━━━━━━━
Price has entered your defined range!
```

---

## Troubleshooting

### Bot not starting?
- Check logs in your cloud dashboard
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct
- Ensure all dependencies installed: `pip install -r requirements.txt`

### Alerts not sending?
- Confirm your Chat ID is correct
- Send a message to your bot first to initialize the chat
- Check if bot is running: `/status`

### Service keeps sleeping (Render)?
- Use UptimeRobot to ping every 5 minutes
- Or consider Oracle Cloud (always free, no sleep)

---

## Comparison Table

| Platform | Free Tier | Sleeps? | Setup Difficulty | Best For |
|----------|-----------|---------|------------------|----------|
| **Render** | ✅ Yes | ⚠️ After 15min | Easy | Quick testing |
| **Railway** | ✅ Trial | ⚠️ Limited hours | Easy | Short-term projects |
| **Oracle Cloud** | ✅ Always | ❌ Never | Medium | Production use |
| **Hugging Face** | ✅ Yes | ❌ Never | Easy | Simple deployments |

**Recommendation**: Start with **Render** for easy setup, then migrate to **Oracle Cloud** for production if you need 24/7 uptime without sleep.

---

## Next Steps

1. Choose your platform
2. Follow the deployment steps
3. Test with `/add BTC 60000 62000`
4. Wait for your first alert! 🎉

For support, check the [README.md](README.md) or open an issue on GitHub.
