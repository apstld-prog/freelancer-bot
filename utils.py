import httpx
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

USD_CACHE = {"rate": None, "timestamp": 0}

def convert_to_usd(amount, currency):
    """Convert given amount from currency to USD using daily cached rate."""
    if not amount or not currency:
        return None
    if currency.upper() == "USD":
        return round(float(amount), 2)

    now = time.time()
    if not USD_CACHE["rate"] or now - USD_CACHE["timestamp"] > 86400:
        try:
            resp = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=10)
            rates = resp.json().get("rates", {})
            USD_CACHE["rate"] = rates
            USD_CACHE["timestamp"] = now
        except Exception:
            return None

    try:
        rate = USD_CACHE["rate"].get(currency.upper())
        if not rate:
            return None
        return round(float(amount) / rate, 2)
    except Exception:
        return None

def job_buttons(job):
    """Generate inline buttons for Telegram message."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 View", url=job.get("affiliate_url")),
            InlineKeyboardButton("💾 Save", callback_data=f"save|{job.get('affiliate_url')}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"delete|{job.get('affiliate_url')}")
        ]
    ])
