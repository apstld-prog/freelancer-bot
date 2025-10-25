import os
import httpx
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger("utils")

# ======================================================================
# GLOBALS
# ======================================================================

CACHED_RATES = {"USD": 1.0}
LAST_RATE_UPDATE = None
RATE_TTL = timedelta(hours=12)  # refresh every 12 hours

FALLBACK_RATES = {
    "USD": 1.0,
    "EUR": 1.07,
    "GBP": 1.27,
    "AUD": 0.65,
    "INR": 0.012,
}

# ======================================================================
# 📊 CURRENCY CONVERSION HELPERS
# ======================================================================

async def fetch_live_rates():
    """Fetch live rates from exchangerate.host API with caching."""
    global CACHED_RATES, LAST_RATE_UPDATE
    try:
        now = datetime.utcnow()
        if LAST_RATE_UPDATE and (now - LAST_RATE_UPDATE) < RATE_TTL:
            return CACHED_RATES  # still fresh

        url = "https://api.exchangerate.host/latest?base=USD"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            if "rates" in data:
                CACHED_RATES = data["rates"]
                LAST_RATE_UPDATE = now
                logger.info(f"[Currency] ✅ Live rates updated ({len(CACHED_RATES)} currencies)")
                return CACHED_RATES
    except Exception as e:
        logger.warning(f"[Currency] Could not update live rates, using fallback: {e}")
    return FALLBACK_RATES


async def convert_to_usd(amount, currency):
    """Convert any currency to USD using live or fallback rates."""
    try:
        if not amount or amount == "N/A":
            return 0.0

        currency = currency.upper().strip()
        rates = await fetch_live_rates()
        rate = rates.get(currency)
        if rate:
            usd_value = round(float(amount) / rate, 2)
        else:
            fallback = FALLBACK_RATES.get(currency, 1.0)
            usd_value = round(float(amount) * fallback, 2)

        return usd_value
    except Exception as e:
        logger.warning(f"[Currency] convert_to_usd error: {e}")
        return 0.0


# ======================================================================
# 🕓 TIME & TEXT UTILITIES
# ======================================================================

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


# ======================================================================
# 📬 TELEGRAM MESSAGE HANDLER
# ======================================================================

async def send_job_to_user(user_id, job):
    """Send formatted job post to Telegram user."""
    try:
        from telegram import Bot
        TOKEN = os.getenv("TELEGRAM_TOKEN")
        if not TOKEN:
            logger.error("[Telegram] ❌ TELEGRAM_TOKEN missing in environment!")
            return False

        bot = Bot(token=TOKEN)

        title = job.get("title", "Untitled")
        desc = job.get("description", "")
        platform = job.get("platform", "Unknown")
        keyword = job.get("keyword", "")
        amount = job.get("budget_amount", 0)
        currency = job.get("budget_currency", "USD")

        usd_value = await convert_to_usd(amount, currency)
        created_at = job.get("created_at", "")
        timeago = format_time_ago(created_at)
        url = job.get("url") or job.get("original_url") or job.get("affiliate_url")

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

        logger.info(f"[Telegram] ✅ Sent job '{title}' to user {user_id}")
        return True

    except TelegramError as e:
        logger.error(f"[Telegram] Error sending job to {user_id}: {e}")
    except Exception as e:
        logger.error(f"[Telegram] send_job_to_user({user_id}) failed: {e}")
    return False


# ======================================================================
# 🌐 ASYNC HTTP & GENERIC HELPERS
# ======================================================================

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
    keys = ["WORKER_INTERVAL", "KEYWORD_FILTER_MODE"]
    for key in keys:
        logger.info(f"{key}={os.getenv(key, 'undefined')}")


async def sleep_safe(seconds):
    """Non-blocking asyncio sleep."""
    try:
        await asyncio.sleep(seconds)
    except Exception:
        pass
