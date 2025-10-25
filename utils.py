import httpx
import os
import logging

logger = logging.getLogger("utils")

# ------------------------------------------------------
# Currency conversion (non-async)
# ------------------------------------------------------
def convert_to_usd(amount, currency):
    """Convert a given amount to USD using a fixed daily rate."""
    if not amount or not currency:
        return None
    try:
        amount = float(amount)
    except Exception:
        return None

    currency = currency.upper().strip()
    rates = {
        "EUR": 1.07,
        "GBP": 1.25,
        "AUD": 0.65,
        "CAD": 0.73,
        "INR": 0.012,
        "USD": 1.0
    }

    rate = rates.get(currency, 1.0)
    usd = round(amount * rate, 2)
    return usd

# ------------------------------------------------------
# Telegram message sending
# ------------------------------------------------------
def build_message_text(job):
    """Return formatted message text with currency and keyword info."""
    platform = job.get("platform", "Unknown").capitalize()
    title = job.get("title", "No title")
    url = job.get("affiliate_url") or job.get("original_url") or "N/A"
    budget = job.get("budget_amount")
    currency = job.get("budget_currency", "USD").upper()
    keyword = job.get("matched_keyword", "N/A")

    # Budget display
    if budget:
        if currency != "USD":
            usd_value = convert_to_usd(budget, currency)
            budget_str = f"{budget} {currency} (~${usd_value} USD)"
        else:
            budget_str = f"{budget} USD"
    else:
        budget_str = "N/A"

    text = (
        f"🌐 <b>{platform}</b>\n"
        f"💼 <b>{title}</b>\n"
        f"💰 <b>Budget:</b> {budget_str}\n"
        f"🔑 <b>Keyword:</b> {keyword}\n"
        f"🔗 <a href='{url}'>View Project</a>"
    )
    return text

async def send_job_to_user(bot, user_id, job):
    """Send formatted job to Telegram user."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    text = build_message_text(job)
    url = job.get("affiliate_url") or job.get("original_url")

    # Inline keyboard buttons
    keyboard = [
        [
            InlineKeyboardButton("🔗 Open", url=url),
            InlineKeyboardButton("💾 Save", callback_data=f"save_{job.get('id', '0')}"),
        ],
        [
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete_{job.get('id', '0')}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        logger.info(f"[Telegram] Sent job to {user_id}")
    except Exception as e:
        logger.error(f"[Telegram] Error sending job to {user_id}: {e}")
