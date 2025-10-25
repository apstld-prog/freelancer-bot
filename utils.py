import os
import httpx
import logging
import asyncio
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger("utils")

# --- Updated, accurate conversion rates ---
CURRENCY_RATES = {
    "USD": 1.0,
    "EUR": 1.07,   # 1 EUR = 1.07 USD
    "GBP": 1.27,   # 1 GBP = 1.27 USD
    "AUD": 0.65,   # 1 AUD = 0.65 USD
    "INR": 0.012,  # 1 INR = 0.012 USD
}


def convert_to_usd(amount, currency):
    """Convert known currency to USD accurately."""
    try:
        if not amount or amount == "N/A":
            return 0.0
        rate = CURRENCY_RATES.get(currency.upper(), 1.0)
        return round(float(amount) * rate, 2)
    except Exception as e:
        logger.warning(f"convert_to_usd error: {e}")
        return 0.0


def format_time_ago(timestamp):
    """Return formatted 'x hours ago' style time."""
    try:
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        seconds = diff.total_seconds()
        if seconds < 60:
            return f"{int(seconds)} sec ago"
        elif seconds < 3600:
            return f"{int(seconds // 60)} min ago"
        elif seconds < 86400:
            return f"{int(seconds // 3600)} hr ago"
        else:
            return f"{int(seconds // 86400)} days ago"
    except Exception:
        return "N/A"


async def send_job_to_user(user_id, job):
    """
    Send formatted job post to Telegram user with full HTML layout.
    Note: simplified to work with worker_runner's call (no 'bot' argument).
    """
    try:
        from telegram import Bot
        TOKEN = os.getenv("TELEGRAM_TOKEN")
        bot = Bot(token=TOKEN)

        title = job.get("title", "Untitled")
        desc = job.get("description", "")
        platform = job.get("platform", "Unknown")
        keyword = job.get("keyword", "")
        amount = job.get("budget_amount", 0)
        currency = job.get("budget_currency", "USD")
        usd_value = convert_to_usd(amount, currency)
        created_at = job.get("created_at", "")
        timeago = format_time_ago(created_at)
        url = job.get("url") or job.get("original_url") or job.get("affiliate_url")

        # ---- Unified format for all job platforms ----
        text = (
            f"<b>🧭 Platform:</b> {platform}\n"
            f"<b>📄 Title:</b> {title}\n"
            f"<b>🔑 Keyword:</b> {keyword}\n"
            f"<b>💰 Budget:</b> {currency} {amount} (~${usd_value} USD)\n"
            f"<b>🕓 Posted:</b> {timeago}\n\n"
            f"{desc.strip()}\n\n"
            f"<a href='{url}'>🔗 View Project</a>"
        )

        buttons = [[InlineKeyboardButton("🔗 View Project", url=url)]]
        reply_markup = InlineKeyboardMarkup(buttons)

        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

        logger.info(f"✅ Sent job '{title}' to user {user_id}")
        return True

    except TelegramError as e:
        logger.error(f"TelegramError sending job to {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error sending job to {user_id}: {e}")
    return False


# ---------- Other shared helpers remain unchanged ----------

async def async_get_json(url, headers=None):
    """Async GET returning parsed JSON."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"HTTPX get_json error: {e}")
        return {}


def safe_get(d, *keys, default=None):
    """Nested dict.get with default."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


def log_env_check():
    """Log environment key variables once."""
    keys = [
        "WORKER_INTERVAL",
        "KEYWORD_FILTER_MODE",
    ]
    for key in keys:
        logger.info(f"{key}={os.getenv(key, 'undefined')}")


async def sleep_safe(seconds):
    """Non-blocking asyncio sleep."""
    try:
        await asyncio.sleep(seconds)
    except Exception:
        pass
