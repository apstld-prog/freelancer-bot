import logging
import httpx
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger("utils")

# --- Currency conversion with fixed exchange rates ---
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.07,
    "GBP": 1.28,
    "INR": 0.012,
    "AUD": 0.65,
    "CAD": 0.73,
}

def convert_to_usd(amount, currency):
    """Convert using static rates to avoid runtime API errors."""
    try:
        rate = EXCHANGE_RATES.get(currency.upper(), 1.0)
        return round(amount * rate, 2)
    except Exception as e:
        logger.warning(f"[Currency] convert_to_usd error: {e}")
        return amount


# --- Telegram job sending utility ---
async def send_job_to_user(bot, user_id, job):
    """Send a formatted job alert with inline buttons."""
    try:
        platform = job.get("platform", "Unknown")
        title = job.get("title", "N/A")
        description = job.get("description", "N/A")[:450]
        keyword = job.get("keyword", "N/A")
        budget_amount = job.get("budget_amount", "N/A")
        budget_usd = job.get("budget_usd", "")
        posted = job.get("posted", "Recently")
        url = job.get("original_url") or job.get("affiliate_url") or job.get("url")

        text = (
            f"🧭 <b>Platform:</b> {platform}\n"
            f"📄 <b>Title:</b> {title}\n"
            f"🔑 <b>Keyword:</b> {keyword}\n"
            f"💰 <b>Budget:</b> {budget_amount} ({budget_usd})\n"
            f"🕓 <b>Posted:</b> {posted}\n\n"
            f"{description}"
        )

        # Inline buttons
        buttons = [
            [
                InlineKeyboardButton("💬 Proposal", url=url),
                InlineKeyboardButton("📄 Original", url=url),
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data=f"save:{url}"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{url}"),
            ],
        ]

        markup = InlineKeyboardMarkup(buttons)

        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        logger.info(f"[Telegram] ✅ Job sent to {user_id}: {title[:40]}")

    except Exception as e:
        logger.error(f"[Telegram] Error sending job to {user_id}: {e}")
        return


# --- Async helper for limited concurrency ---
async def gather_with_limit(limit, *tasks):
    """Run async tasks with a concurrency limit."""
    semaphore = asyncio.Semaphore(limit)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(t) for t in tasks))
