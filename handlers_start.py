import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import get_or_create_user_by_tid
from config import TRIAL_DAYS

log = logging.getLogger("handlers_start")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    get_or_create_user_by_tid(uid)

    text = (
        "Ã°Å¸â€˜â€¹ *Welcome to Freelancer Alert Bot!*\n\n"
        f"Ã°Å¸Å½Â You have a *{TRIAL_DAYS}-day free trial*.\n"
        "Automatically finds matching freelance jobs and sends instant alerts.\n\n"
        "Use /help to learn how it works.\n"
        "________________________________________\n"
        "Ã°Å¸Å¸Â© *Keywords*   Ã¢Å¡â„¢Ã¯Â¸Â *Settings*\n"
    )

    kb = [
        [
            InlineKeyboardButton("Ã°Å¸Å¸Â© Keywords", callback_data="ui:keywords"),
            InlineKeyboardButton("Ã¢Å¡â„¢Ã¯Â¸Â Settings", callback_data="ui:settings"),
        ]
    ]

    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


