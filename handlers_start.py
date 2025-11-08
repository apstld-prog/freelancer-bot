import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import get_or_create_user

log = logging.getLogger("handlers_start")

START_TEXT = (
    "👋 Welcome to Freelancer Alert Bot!\n"
    "🎁 You have a 10-day free trial.\n\n"
    "Automatically finds matching freelance jobs from top platforms "
    "and sends you instant alerts with affiliate-safe links.\n\n"
    "Use /help to see how it works.\n"
    "________________________________________\n"
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id)

    keyboard = [
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="ui:keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="ui:settings"),
        ]
    ]

    await update.message.reply_text(
        START_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
