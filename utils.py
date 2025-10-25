import logging
import hashlib
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("utils")


async def send_job_to_user(bot, user_id, job):
    """Send a job posting to a Telegram user with full inline buttons (View, Save, Delete)."""
    try:
        title = job.get("title", "Untitled")
        platform = job.get("platform", "Unknown")
        budget = job.get("budget_display") or job.get("budget_amount")
        currency = job.get("budget_currency", "")
        usd_val = job.get("budget_usd")

        if not budget and usd_val:
            budget = f"~${usd_val:.2f}"
        elif not budget:
            budget = "N/A"
        else:
            if usd_val:
                budget = f"{budget} ({usd_val:.2f} USD)"

        url = job.get("affiliate_url") or job.get("original_url") or job.get("url")
        desc = job.get("description", "").strip()
        if len(desc) > 500:
            desc = desc[:500] + "…"

        created_at = job.get("created_at", "Unknown time")
        keyword = job.get("matched_keyword", "")
        keyword_line = f"🔎 Keyword: {keyword}\n" if keyword else ""

        # Main message text
        message = (
            f"💼 <b>{title}</b>\n"
            f"🌍 Platform: {platform}\n"
            f"💰 Budget: {budget}\n"
            f"{keyword_line}"
            f"🕒 Posted: {created_at}\n\n"
            f"{desc}"
        )

        # Safe callback data
        hash_key = hashlib.md5(str(url).encode()).hexdigest()[:10]
        callback_save = f"save_{hash_key}"
        callback_delete = f"delete_{hash_key}"

        # Inline buttons layout
        buttons = [
            [
                InlineKeyboardButton("🌐 View Job", url=url or "https://freelancer.com"),
            ],
            [
                InlineKeyboardButton("💾 Save", callback_data=callback_save),
                InlineKeyboardButton("❌ Delete", callback_data=callback_delete),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        # Send message
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )

        logger.info(f"[Telegram] ✅ Sent job to {user_id}: {title[:40]}")

    except Exception as e:
        logger.error(f"[Telegram] Error sending job to {user_id}: {e}")


async def send_chunked_jobs(bot, user_id, jobs, delay=2):
    """Send multiple jobs sequentially to avoid Telegram flood limits."""
    for job in jobs:
        await send_job_to_user(bot, user_id, job)
        await asyncio.sleep(delay)
