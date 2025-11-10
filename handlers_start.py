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
        "ðŸ‘‹ *Welcome to Freelancer Alert Bot!*\n\n"
        f"ðŸŽ You have a *{TRIAL_DAYS}-day free trial*.\n"
        "Automatically finds matching freelance jobs and sends instant alerts.\n\n"
        "Use /help to learn how it works.\n"
        "________________________________________\n"
        "ðŸŸ© *Keywords*   âš™ï¸ *Settings*\n"
    )

    kb = [
        [
            InlineKeyboardButton("ðŸŸ© Keywords", callback_data="ui:keywords"),
            InlineKeyboardButton("âš™ï¸ Settings", callback_data="ui:settings"),
        ]
    ]

    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )

