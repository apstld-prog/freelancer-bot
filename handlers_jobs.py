import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import get_session
from db_events import get_recent_jobs_for_user

logger = logging.getLogger("handlers.jobs")


def jobs_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="back_start")]
    ])


async def jobs_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    telegram_id = query.from_user.id

    with get_session() as session:
        jobs = get_recent_jobs_for_user(session, telegram_id, limit=10)

    if not jobs:
        await query.edit_message_text(
            "No recent jobs found.",
            reply_markup=jobs_menu()
        )
        return

    text_lines = ["*Your Recent Jobs:*", ""]
    for job in jobs:
        text_lines.append(
            f"• *{job.title}*\n"
            f"Platform: {job.platform}\n"
            f"Budget: {job.budget_usd or 'N/A'} USD\n"
            f"[Open Link]({job.affiliate_url or job.original_url})\n"
        )

    await query.edit_message_text(
        "\n".join(text_lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=jobs_menu()
    )


