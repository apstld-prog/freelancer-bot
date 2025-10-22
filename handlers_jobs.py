# handlers_jobs.py
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from utils import format_budget, format_relative_time, escape_html

log = logging.getLogger("handlers_jobs")

DEFAULT_URL = "https://www.peopleperhour.com/"

def job_to_message(job):
    """Format a job dictionary into Telegram message text and keyboard."""
    title = escape_html(job.get("title", "(untitled)"))
    desc = escape_html(job.get("description", ""))
    keyword = escape_html(job.get("matched_keyword", ""))
    source = job.get("source", "Unknown")
    budget_min = job.get("budget_min")
    budget_max = job.get("budget_max")
    ccy = job.get("budget_currency", "")
    posted = job.get("time_submitted")

    # Budget formatting
    budget_str = format_budget(budget_min, budget_max, ccy)

    # Time formatting
    posted_str = format_relative_time(posted) if posted else ""

    # Build text message (same structure as before)
    text = (
        f"<b>{title}</b>\n"
        f"<b>Budget:</b> {budget_str}\n"
        f"<b>Source:</b> {source}\n"
        f"<b>Match:</b> {keyword}\n"
        f"📝 {desc}\n"
    )
    if posted_str:
        text += f"<i>{posted_str}</i>"

    # --- Keyboard buttons ---
    url = job.get("affiliate_url") or job.get("original_url") or DEFAULT_URL
    if not url.startswith("http"):
        url = DEFAULT_URL

    buttons = [
        [
            InlineKeyboardButton("📄 Proposal", url=url),
            InlineKeyboardButton("🔗 Original", url=url),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{job.get('id', '0')}"),
            InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(buttons)
    return text, reply_markup


async def send_job(bot, chat_id, job):
    """Safely send a single job message to Telegram."""
    try:
        text, keyboard = job_to_message(job)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.warning(f"Failed to send job ({job.get('id')}): {e}")


async def send_jobs(bot, chat_id, jobs, source=None):
    """Send multiple jobs with detailed logging."""
    if not jobs:
        log.info(f"No jobs to send (source={source})")
        return

    log.info(f"Sending {len(jobs)} jobs to Telegram (source={source})")
    for job in jobs:
        await send_job(bot, chat_id, job)
