import logging
import httpx
import asyncio
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("utils")

# ----------------------------------------------------------
# Telegram message sending helper
# ----------------------------------------------------------

async def send_job_to_user(app, chat_id, message, job):
    """
    Στέλνει αγγελία στον χρήστη με inline κουμπιά.
    Χρησιμοποιείται από όλους τους workers.
    """
    try:
        buttons = [
            [
                InlineKeyboardButton("🔗 View Job", url=job.get("affiliate_url") or job.get("original_url")),
            ],
            [
                InlineKeyboardButton("💾 Save", callback_data=f"save_{job.get('id')}"),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{job.get('id')}"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(buttons)
        await app.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)
        logger.info(f"[send_job_to_user] Sent {job.get('platform')} job to {chat_id} (kw={job.get('matched_keyword')})")

    except Exception as e:
        logger.error(f"[send_job_to_user] Failed to send message to {chat_id}: {e}")


# ----------------------------------------------------------
# Helper functions
# ----------------------------------------------------------

def posted_ago(dt: datetime) -> str:
    if not dt:
        return "N/A"
    diff = datetime.utcnow() - dt.replace(tzinfo=None)
    seconds = diff.total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    else:
        return f"{int(seconds // 86400)}d ago"


def get_telegram_text(job: dict) -> str:
    """Δημιουργεί το μήνυμα αγγελίας σε ενιαία μορφή"""
    title = job.get("title") or "N/A"
    desc = job.get("description") or "No description available."
    budget = job.get("budget_amount") or "N/A"
    currency = job.get("budget_currency") or "USD"
    usd_val = job.get("budget_usd")

    budget_line = f"💰 Budget: {budget} {currency}"
    if usd_val:
        budget_line += f" (~${usd_val} USD)"

    platform = job.get("platform") or "Unknown"
    kw = job.get("matched_keyword") or "N/A"
    posted = job.get("posted_ago") or "N/A"

    lines = [
        f"💼 {title}",
        budget_line,
        f"🌍 Source: {platform}",
        f"🔑 Match: {kw}",
        f"🕒 Posted: {posted}",
        "",
        f"📝 {desc.strip()[:800]}",
    ]
    return "\n".join(lines)


def now_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def async_run(coro):
    """Τρέχει coroutine με ασφάλεια χωρίς runtime conflicts"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.ensure_future(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)
