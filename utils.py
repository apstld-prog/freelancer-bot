import os
import httpx
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

USD_EXCHANGE_RATES = {
    "EUR": 1.09,
    "GBP": 1.28,
    "AUD": 0.66,
    "CAD": 0.73,
    "INR": 0.012,
    "JPY": 0.0067,
}

def convert_to_usd(amount, currency):
    try:
        if not amount or not currency:
            return None
        currency = currency.upper()
        if currency == "USD":
            return amount
        rate = USD_EXCHANGE_RATES.get(currency)
        if not rate:
            return None
        return round(amount * rate, 2)
    except Exception:
        return None

async def send_job_to_user(bot_token, user_id, job):
    bot = Bot(token=bot_token)
    title = job.get("title", "No title")
    desc = job.get("description", "No description")[:400]
    url = job.get("affiliate_url") or job.get("original_url")
    budget = job.get("budget_display", "Budget: N/A")
    keyword = job.get("matched_keyword", "N/A")
    platform = job.get("platform", "").capitalize()

    text = (
        f"📢 <b>{title}</b>\n"
        f"💼 Platform: {platform}\n"
        f"💰 {budget}\n"
        f"🔑 Keyword: <code>{keyword}</code>\n\n"
        f"{desc}\n\n"
        f"<a href='{url}'>Open job link</a>"
    )

    keyboard = [
        [
            InlineKeyboardButton("💾 Save", callback_data=f"save|{url}"),
            InlineKeyboardButton("❌ Delete", callback_data=f"delete|{url}")
        ],
        [
            InlineKeyboardButton("🌐 Open", url=url),
            InlineKeyboardButton("🔗 Visit", url=url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=False
        )
    except Exception as e:
        print(f"[Telegram] Error sending job to {user_id}: {e}")
