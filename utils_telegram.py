import os
import time
import logging
import httpx
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError, RetryAfter

# -----------------------------------------------------------------------------
# Telegram utility for sending job alerts to users
# -----------------------------------------------------------------------------

logger = logging.getLogger("utils_telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")

bot = Bot(token=BOT_TOKEN)

# -----------------------------------------------------------------------------
# Helper: format job message text
# -----------------------------------------------------------------------------
def format_job_message(job, platform_name: str):
    title = job.get("title") or "(no title)"
    url = job.get("affiliate_url") or job.get("original_url") or ""
    budget_amount = job.get("budget_amount")
    budget_currency = job.get("budget_currency")
    budget_usd = job.get("budget_usd")
    keyword = job.get("matched_keyword", "")
    created_at = job.get("created_at", "")

    # Budget formatting
    if budget_amount and budget_currency:
        budget_str = f"💰 Budget: {budget_amount} {budget_currency}"
        if budget_usd and budget_currency != "USD":
            budget_str += f" (~${budget_usd:.0f} USD)"
    else:
        budget_str = "💰 Budget: Not specified"

    text = (
        f"📢 <b>{platform_name}</b>\n"
        f"<b>{title}</b>\n\n"
        f"{budget_str}\n"
    )

    if keyword:
        text += f"🔍 Keyword: {keyword}\n"
    if created_at:
        text += f"🕓 {created_at}\n"

    if url:
        text += f"\n<a href=\"{url}\">🔗 View Job</a>"

    return text


# -----------------------------------------------------------------------------
# Helper: send a single message safely
# -----------------------------------------------------------------------------
async def safe_send_message(user_id: int, text: str, reply_markup=None):
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=reply_markup,
        )
        await asyncio.sleep(0.5)  # Anti-ban small delay
    except RetryAfter as e:
        delay = int(e.retry_after) + 1
        logger.warning(f"Rate limit hit. Sleeping {delay}s...")
        time.sleep(delay)
    except TelegramError as e:
        logger.warning(f"Failed to send message to {user_id}: {e}")


# -----------------------------------------------------------------------------
# Main: send jobs to user
# -----------------------------------------------------------------------------
async def send_jobs_to_user(user_id: int, jobs: list, platform_name: str):
    if not jobs:
        return 0

    sent_count = 0
    for job in jobs[:10]:
        text = format_job_message(job, platform_name)
        url = job.get("affiliate_url") or job.get("original_url")

        buttons = []
        if url:
            buttons = [[InlineKeyboardButton("🔗 Open Job", url=url)]]

        markup = InlineKeyboardMarkup(buttons) if buttons else None

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=markup,
            )
            sent_count += 1
            time.sleep(0.5)  # Anti-ban
        except TelegramError as e:
            logger.warning(f"send_message failed for {user_id}: {e}")
            continue

    logger.info(f"[{platform_name}] sent {sent_count} jobs → {user_id}")
    return sent_count


# -----------------------------------------------------------------------------
# Fallback: HTTP sending (non-async safe mode)
# -----------------------------------------------------------------------------
def send_jobs_to_user_sync(user_id: int, jobs: list, platform_name: str):
    """
    Synchronous version (used by worker_runner if asyncio loop unavailable)
    """
    if not jobs:
        return 0

    sent_count = 0
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    for job in jobs[:10]:
        text = format_job_message(job, platform_name)
        job_url = job.get("affiliate_url") or job.get("original_url")

        reply_markup = None
        if job_url:
            reply_markup = {
                "inline_keyboard": [[{"text": "🔗 Open Job", "url": job_url}]]
            }

        payload = {
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
            "reply_markup": reply_markup,
        }

        try:
            response = httpx.post(url, json=payload, timeout=15)
            if response.status_code != 200:
                logger.warning(f"Telegram sendMessage failed: {response.text}")
            else:
                sent_count += 1
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Error sending to {user_id}: {e}")
            continue

    logger.info(f"[{platform_name}] sent {sent_count} jobs → {user_id}")
    return sent_count
