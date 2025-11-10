import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from handlers_settings import settings_menu
from handlers_help import help_menu
from db_keywords import get_keywords

log = logging.getLogger("handlers_ui")


async def handle_ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "ui:back_home":
        await query.message.reply_text(
            "🏠 Main Menu\nChoose an option:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🟩 Keywords", callback_data="ui:keywords"),
                    InlineKeyboardButton("⚙️ Settings", callback_data="ui:settings"),
                ],
                [InlineKeyboardButton("❓ Help", callback_data="ui:help")],
            ]),
            parse_mode="Markdown"
        )
        return

    if data == "ui:keywords":
        uid = query.from_user.id
        kws = get_keywords(uid)
        kws_text = ", ".join(kws) if kws else "(none)"
        await query.message.reply_text(
            f"*Your keywords:*\n{kws_text}",
            parse_mode="Markdown"
        )
        return

    if data == "ui:settings":
        await settings_menu(update, context)
        return

    if data == "ui:help":
        await help_menu(update, context)
        return


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fallback for UI text messages
    await update.message.reply_text(
        "Use /start to return to the main menu.",
    )
