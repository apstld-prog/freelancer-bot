import logging
import os
import httpx
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot
from db_keywords import get_all_user_keywords

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

CURRENCY_RATES = {"USD": 1.0}
CURRENCY_API_URL = "https://api.exchangerate.host/latest?base=USD"


# =======================================================
# Currency and conversion
# =======================================================
async def update_currency_rates():
    """Update FX rates from exchangerate.host"""
    global CURRENCY_RATES
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(CURRENCY_API_URL)
            if resp.status_code == 200:
                CURRENCY_RATES = resp.json().get("rates", {})
                logging.info(f"[utils] ✅ Updated currency rates ({len(CURRENCY_RATES)} entries)")
    except Exception as e:
        logging.warning(f"[utils] ⚠️ Failed to update FX rates: {e}")


def convert_to_usd(amount, currency):
    """Convert arbitrary currency to USD"""
    try:
        rate = CURRENCY_RATES.get(currency.upper(), 1)
        if rate == 0:
            return amount
        return round(amount / rate, 2)
    except Exception:
        return amount


# =======================================================
# Formatting helpers
# =======================================================
def format_time_ago(created_at):
    """Display human readable relative time"""
    if not created_at:
        return "N/A"
    now = datetime.utcnow()
    delta = now - created_at
    if delta.days >= 2:
        return f"{delta.days} days ago"
    if delta.days == 1:
        return "1 day ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} hours ago"
    minutes = (delta.seconds % 3600) // 60
    return f"{minutes} min ago"


def build_job_message(job):
    """Compose formatted message body"""
    title = job.get("title", "Untitled")
    desc = job.get("description", "")
    budget = job.get("budget_usd", 0)
    original = job.get("budget_amount", 0)
    currency = job.get("budget_currency", "USD")
    keyword = job.get("keyword", "")
    source = job.get("platform", "Unknown")
    created_at = job.get("created_at")
    ago = format_time_ago(created_at)

    return (
        f"🧾 <b>{title}</b>\n"
        f"<b>Budget:</b> {original:.2f} {currency}  ({budget:.2f} USD)\n"
        f"<b>Source:</b> {source}\n"
        f"<b>Match:</b> {keyword}\n"
        f"🕒 <i>{ago}</i>\n\n"
        f"{desc.strip()[:500]}"
    )


def build_job_buttons(job):
    """Unified Telegram buttons layout"""
    proposal_url = job.get("proposal_url") or job.get("affiliate_url") or "#"
    original_url = job.get("original_url") or job.get("url") or "#"
    job_id = job.get("id", "0")

    keyboard = [
        [
            InlineKeyboardButton("📄 Proposal", url=proposal_url),
            InlineKeyboardButton("🔗 Original", url=original_url),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data=f"save_{job_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"del_{job_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# =======================================================
# Messaging helpers
# =======================================================
async def send_job_to_user(bot_instance, user_id, text, job):
    """Send job message to one user"""
    try:
        buttons = build_job_buttons(job)
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=buttons,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logging.info(f"[send_job_to_user] ✅ Sent {job.get('platform')} job to {user_id}")
    except Exception as e:
        logging.error(f"[send_job_to_user] ❌ Failed to send to {user_id}: {e}")
