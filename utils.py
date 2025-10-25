# utils.py
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ---------------------------------------------
# ✅ Static USD conversion (no external API)
# ---------------------------------------------
def convert_to_usd(amount, currency):
    """Static fallback conversion using approximate rates."""
    STATIC_RATES = {"EUR": 1.10, "GBP": 1.25, "AUD": 0.65, "CAD": 0.73, "JPY": 0.0066}
    try:
        if not amount or not currency:
            return None
        currency = currency.upper()
        if currency == "USD":
            return float(amount)
        rate = STATIC_RATES.get(currency)
        if not rate:
            return None
        return round(float(amount) * rate, 2)
    except Exception as e:
        logger.warning(f"Currency convert_to_usd error: {e}")
        return None


# ---------------------------------------------
# 💰 Budget formatter (safe conversion)
# ---------------------------------------------
def format_budget(amount_min, amount_max, currency):
    """Formats original + USD safely."""
    try:
        # Handle missing / N/A data gracefully
        if not amount_min or str(amount_min).upper() == "N/A":
            return f"Budget: N/A"

        base = f"{amount_min}–{amount_max} {currency}" if amount_max else f"{amount_min} {currency}"
        if currency and currency.upper() != "USD":
            usd_val = convert_to_usd(amount_max or amount_min, currency)
            if usd_val:
                base += f" (~${usd_val} USD)"
        return base
    except Exception as e:
        logger.warning(f"format_budget error: {e}")
        return f"Budget: N/A"


# ---------------------------------------------
# 💬 Send formatted job post to Telegram
# ---------------------------------------------
async def send_job_to_user(bot, chat_id, job):
    """Send formatted job card to Telegram user."""
    try:
        title = job.get("title", "Untitled")
        platform = job.get("platform", "Unknown")
        desc = job.get("description", "")[:300]
        keyword = job.get("keyword") or "(missing)"
        budget_amount = job.get("budget_amount", "N/A")
        budget_currency = job.get("budget_currency", "USD")
        budget_max = job.get("budget_max", None)
        budget_text = format_budget(budget_amount, budget_max, budget_currency)
        url = job.get("url") or job.get("affiliate_url") or job.get("original_url")

        text = (
            f"💼 <b>{title}</b>\n"
            f"🌐 <b>Platform:</b> {platform}\n"
            f"🔑 <b>Keyword:</b> {keyword}\n"
            f"💰 <b>{budget_text}</b>\n\n"
            f"{desc}..."
        )

        buttons = [
            [
                InlineKeyboardButton("💬 Proposal", callback_data="proposal"),
                InlineKeyboardButton("🌐 Original", url=url),
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data="save"),
                InlineKeyboardButton("🗑 Delete", callback_data="delete"),
            ],
        ]

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )

    except Exception as e:
        logger.error(f"send_job_to_user error: {e}")
