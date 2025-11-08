import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import get_or_create_user

log = logging.getLogger("handlers_settings")


# ---------------------------------------------------------
# SETTINGS MENU HANDLER
# ---------------------------------------------------------
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    get_or_create_user(telegram_id)

    text = (
        "⚙️ **Settings**\n\n"
        "Additional settings will become available soon."
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Back", callback_data="ui:back_main")]
    ]

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
