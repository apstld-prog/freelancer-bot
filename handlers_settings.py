from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db_keywords import get_keywords_for_user
from db import get_session, get_or_create_user_by_tid


def settings_menu(user_settings):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 Keywords", callback_data="settings_keywords"),
            InlineKeyboardButton("⏱ Interval", callback_data="settings_interval")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="back_start")
        ]
    ])


async def settings_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    telegram_id = query.from_user.id

    with get_session() as session:
        user = get_or_create_user_by_tid(session, telegram_id)
        keywords = get_keywords_for_user(session, user.id)

    text = (
        "*Settings*\n\n"
        f"Your keywords: {', '.join(keywords) if keywords else 'None'}\n\n"
        "Use the menu below to modify your settings."
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=settings_menu(user),
        disable_web_page_preview=True
    )

