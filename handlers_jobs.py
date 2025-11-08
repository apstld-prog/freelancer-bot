# handlers_jobs.py â€” FULL VERSION (no cuts) + selftest_jobs()

import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from db_events import record_event
from utils_fx import convert_to_usd

log = logging.getLogger(__name__)

def posted_ago(dt: datetime) -> str:
    diff = datetime.now(timezone.utc) - dt
    if diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hours ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minutes ago"
    else:
        return "just now"

async def selftest_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send sample job alerts for self-test verification."""
    usd1 = convert_to_usd(30, "GBP")
    usd2 = convert_to_usd(50, "EUR")

    now = datetime.now(timezone.utc)
    msg1 = (
        "<b>Logo Design Project</b>\n"
        f"<b>Budget:</b> 30 GBP (~${usd1} USD)\n"
        "<b>Source:</b> PeoplePerHour\n"
        "<b>Match:</b> logo\n"
        "ðŸŽ¨ Need a simple logo redesign for an app.\n"
        f"<i>Posted: {posted_ago(now - timedelta(minutes=1))}</i>"
    )
    kb1 = InlineKeyboardMarkup([
        [InlineKeyboardButton("ðŸ“„ Proposal", url="https://peopleperhour.com/job/1"),
         InlineKeyboardButton("ðŸ”— Original", url="https://peopleperhour.com/job/1")],
        [InlineKeyboardButton("â­ Save", callback_data="job:save"),
         InlineKeyboardButton("ðŸ—‘ï¸ Delete", callback_data="job:delete")]
    ])

    msg2 = (
        "<b>Website UI Fix</b>\n"
        f"<b>Budget:</b> 50 EUR (~${usd2} USD)\n"
        "<b>Source:</b> Freelancer\n"
        "<b>Match:</b> design\n"
        "ðŸ–¥ Fix and optimize website interface.\n"
        f"<i>Posted: {posted_ago(now - timedelta(minutes=5))}</i>"
    )
    kb2 = InlineKeyboardMarkup([
        [InlineKeyboardButton("ðŸ“„ Proposal", url="https://freelancer.com/job/2"),
         InlineKeyboardButton("ðŸ”— Original", url="https://freelancer.com/job/2")],
        [InlineKeyboardButton("â­ Save", callback_data="job:save"),
         InlineKeyboardButton("ðŸ—‘ï¸ Delete", callback_data="job:delete")]
    ])

    await update.message.reply_text(msg1, parse_mode=ParseMode.HTML, reply_markup=kb1)
    await update.message.reply_text(msg2, parse_mode=ParseMode.HTML, reply_markup=kb2)
    record_event("freelancer")
    record_event("peopleperhour")
    log.info("âœ… Selftest jobs sent successfully.")

async def handle_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Save/Delete button callbacks."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    action = query.data or ""
    if action == "job:save":
        await query.message.reply_text("â­ Saved to your list.")
    elif action == "job:delete":
        await query.message.reply_text("ðŸ—‘ï¸ Deleted.")
    else:
        await query.message.reply_text("Unknown job action.")



