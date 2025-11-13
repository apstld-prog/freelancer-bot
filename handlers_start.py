from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from datetime import datetime, timedelta

from utils import get_or_create_user_by_tid, get_user, set_user_setting
from config import TRIAL_DAYS


# -------------------------------------------------
# /start command
# -------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point for /start.
    - Ensures the user exists in app_user table
    - Ensures trial_until is set
    - Shows the exact UI text/layout you requested
    """
    tid = update.effective_user.id

    # 1) Ensure user row exists (app_user)
    get_or_create_user_by_tid(tid)

    # 2) Load user data (including trial_until)
    user = get_user(tid)

    now = datetime.utcnow()

    # If no user or no trial_until, start / refresh trial
    trial_until = None
    if user:
        trial_until = user.get("trial_until")

    if not trial_until:
        trial_until = now + timedelta(days=TRIAL_DAYS)
        # store in DB
        set_user_setting(tid, "trial_until", trial_until)

    remaining_days = max((trial_until - now).days, 0)

    # UI TEXT — EXACTLY AS YOU WANT IT
    text = (
        "👋 Welcome to *Freelancer Alert Bot!*\n\n"
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

    # Normal message
    if update.message:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )

    # Button callback
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )


# -------------------------------------------------
# Handler registration function (used by server.py)
# -------------------------------------------------
def register_start_handlers(application):
    application.add_handler(CommandHandler("start", start))
