"""
discord_notifier.py — Send alerts to Discord via Webhook.
"""

import os
import requests
from logger import get_logger

log = get_logger("discord")

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_alert(asset: str, price: float, condition: str, target: float):
    """Send an alert message to Discord."""
    if not WEBHOOK_URL:
        log.warning("Discord webhook URL not configured")
        return False
    
    color = 0x00ff00 if "entered" in condition else 0xff0000
    
    embed = {
        "title": f"🔔 Price Alert: {asset}",
        "description": f"**{asset}** has {condition}!\n\n💰 Current Price: **${price:,.4f}**\n🎯 Target: **${target:,.4f}**",
        "color": color,
        "footer": {
            "text": "Multi-Asset Alert Bot"
        }
    }
    
    payload = {
        "embeds": [embed]
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            log.info(f"Discord alert sent for {asset}")
            return True
        else:
            log.error(f"Discord API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        log.error(f"Failed to send Discord message: {e}")
        return False
