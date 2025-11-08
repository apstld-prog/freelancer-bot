import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from utils import get_or_create_user
from config import TRIAL_DAYS

logger = logging.getLogger("handlers.start")


def start_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="settings"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("📘 Help", callback_data="help"),
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update)

    # Trial
    if user.trial_until is None:
        user.trial_until = datetime.now(timezone.utc)
        await update.message.reply_text("Initializing your free trial...")
    else:
        pass

    text = (
        "👋 Welcome to Freelancer Alert Bot!\n"
        f"🎁 You have a *{TRIAL_DAYS}-day free trial*.\n\n"
        "Automatically finds matching freelance jobs from top platforms and sends\n"
        "you instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works.\n"
        "________________________________________\n\n"
        "🟩 Keywords  ⚙️ Settings   📘 Help\n"
    )

    if update.message:
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=start_menu()
        )
    else:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=start_menu()
        )


async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

