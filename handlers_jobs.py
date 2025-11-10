import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import save_job, delete_saved_job, wrap_affiliate_link
from db_events import record_event

log = logging.getLogger("handlers_jobs")


# ---------------------------------------------------------
# Format "posted ago"
# ---------------------------------------------------------
def format_posted_ago(ts: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - ts
    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{int(minutes)} minutes ago"
    hours = minutes // 60
    if hours < 24:
        return f"{int(hours)} hours ago"
    days = hours // 24
    return f"{int(days)} days ago"


# ---------------------------------------------------------
# RENDER JOB CARD
# ---------------------------------------------------------
async def send_job_card(update: Update, context: ContextTypes.DEFAULT_TYPE, job):
    uid = update.effective_user.id

    title = job.title or "(no title)"
    desc = job.description or "(no description)"
    platform = job.platform or "Unknown"
    match_kw = job.match_keyword or "(none)"

    # Budget
    if job.budget_amount:
        budget_str = f"{job.budget_amount}Ã¢â‚¬â€œ{job.budget_amount} {job.budget_currency} ({job.budget_usd}$)"
    else:
        budget_str = "N/A"

    posted = format_posted_ago(job.created_at)

    # CARD TEXT
    text = (
        f"*{title}*\n"
        f"Ã°Å¸â€™Â° *Budget:* {budget_str}\n"
        f"Ã°Å¸Å’Â *Source:* {platform}\n"
        f"Ã°Å¸â€Â *Match:* {match_kw}\n"
        f"Ã°Å¸â€œÂ {desc}\n"
        f"Ã¢ÂÂ±Ã¯Â¸Â {posted}\n"
        "________________________________________"
    )

    proposal_url = wrap_affiliate_link(job.original_url)
    original_url = wrap_affiliate_link(job.original_url)

    kb = [
        [
            InlineKeyboardButton("Proposal", url=proposal_url),
            InlineKeyboardButton("Original", url=original_url)
        ],
        [
            InlineKeyboardButton("Ã¢Â­Â Save", callback_data=f"act:save:{job.id}"),
            InlineKeyboardButton("Ã°Å¸â€”â€˜Ã¯Â¸Â Delete", callback_data=f"act:del:{job.id}")
        ]
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


# ---------------------------------------------------------
# SAVE / DELETE CALLBACKS
# ---------------------------------------------------------
async def handle_job_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    _, action, job_id = parts
    uid = query.from_user.id

    try:
        if action == "save":
            save_job(uid, job_id)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.edit_message_text("Ã¢Å“â€¦ Job saved.")
        elif action == "del":
            delete_saved_job(uid, job_id)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.edit_message_text("Ã°Å¸â€”â€˜Ã¯Â¸Â Job deleted.")
    except Exception as e:
        log.error(f"Job action failed: {e}")


