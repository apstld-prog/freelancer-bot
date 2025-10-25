import requests
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("utils")

def convert_to_usd(amount, currency):
    """Convert given amount to USD if currency is not already USD."""
    if not amount or not currency:
        return None
    currency = currency.strip().upper()
    if currency == "USD":
        return f"{amount} USD"

    try:
        rate_resp = requests.get("https://api.exchangerate.host/latest?base=" + currency)
        rate_data = rate_resp.json()
        rate = rate_data["rates"].get("USD")
        if not rate:
            return f"{amount} {currency}"
        usd_value = float(amount) * rate
        return f"{amount} {currency} (~{usd_value:.2f} USD)"
    except Exception as e:
        logger.warning(f"Currency convert_to_usd error: {e}")
        return f"{amount} {currency}"

def build_job_keyboard(job):
    """Return Telegram inline keyboard for a job post."""
    url = job.get("affiliate_url") or job.get("original_url") or job.get("url", "")
    job_id = str(job.get("id", "0"))
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 View", url=url),
            InlineKeyboardButton("💾 Save", callback_data=f"save_{job_id}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{job_id}")
        ]
    ])

async def send_job_to_user(bot, user_id, job):
    """Send formatted job message to Telegram user."""
    try:
        title = job.get("title", "Untitled")
        platform = job.get("platform", "").capitalize()
        desc = job.get("description", "")[:400] + "..."
        budget = job.get("budget_amount") or "N/A"
        currency = job.get("budget_currency", "USD")
        converted = convert_to_usd(budget, currency)
        keyword = job.get("matched_keyword", "")
        time_str = job.get("created_at", "N/A")
        text = (
            f"<b>{platform}</b>\n"
            f"💼 <b>{title}</b>\n\n"
            f"{desc}\n\n"
            f"💰 <b>Budget:</b> {converted}\n"
            f"⏰ <b>Posted:</b> {time_str}\n"
            f"🔑 <b>Keyword:</b> {keyword}"
        )
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=build_job_keyboard(job),
            parse_mode="HTML",
            disable_web_page_preview=False
        )
    except Exception as e:
        logger.error(f"[Telegram] Error sending job to {user_id}: {e}")
