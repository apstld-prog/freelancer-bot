from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from datetime import datetime, timedelta
from db import get_or_create_user_by_tid
from config import TRIAL_DAYS


# -------------------------------------------------
# /start command
# -------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user_by_tid(update.effective_user.id)
    now = datetime.utcnow()
    trial_until = user.trial_until or (now + timedelta(days=TRIAL_DAYS))
    user.trial_until = trial_until

    remaining_days = (trial_until - now).days

    text = (
        f"👋 Welcome to *Freelancer Alert Bot!*\n\n"
        f"🎁 You have a *{remaining_days}-day free trial*.\n"
        "Automatically finds matching freelance jobs from top platforms "
        "and sends you instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works."
        "\n________________________________________\n"
        "🟩 Keywords  ⚙️ Settings  📘 Help"
    )

    keyboard = [
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [InlineKeyboardButton("📘 Help", callback_data="help")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # If start is called via button or app menu
    if update.message:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )


# -------------------------------------------------
# Handler registration function (THIS WAS MISSING)
# -------------------------------------------------
def register_start_handlers(application):
    application.add_handler(CommandHandler("start", start))
