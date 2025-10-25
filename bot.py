import logging
import os
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
)

from db import get_or_create_user_by_tid
from utils import format_job_message, fetch_demo_jobs

logger = logging.getLogger(__name__)

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)

# ------------------------------------------------------
# Buttons layout
# ------------------------------------------------------
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="add_keywords"),
            InlineKeyboardButton("💾 Saved", callback_data="saved"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("📞 Contact", callback_data="contact"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="help"),
            InlineKeyboardButton("🔥 Admin", callback_data="admin"),
        ]
    ])


# ------------------------------------------------------
# Commands
# ------------------------------------------------------
async def start(update: Update, context: CallbackContext):
    user = get_or_create_user_by_tid(update.effective_user.id)
    trial_days = 10
    expiry = datetime.utcnow() + timedelta(days=trial_days)

    text = (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        f"🎁 You have a <b>{trial_days}-day free trial</b>.\n"
        f"Expires: <b>{expiry.strftime('%Y-%m-%d %H:%M UTC')}</b>\n\n"
        "The bot automatically sends you jobs matching your keywords "
        "from top freelance platforms.\n\n"
        "Use /selftest to test job cards."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())


async def selftest(update: Update, context: CallbackContext):
    jobs = await fetch_demo_jobs()
    for job in jobs:
        msg, markup = format_job_message(job)
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=markup)


# ------------------------------------------------------
# Callbacks
# ------------------------------------------------------
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "add_keywords":
        await query.edit_message_text("Use /addkeyword <words> to add keywords.")
    elif data == "saved":
        await query.edit_message_text("Your saved list is empty.")
    elif data == "settings":
        await query.edit_message_text("Settings section coming soon.")
    elif data == "contact":
        await query.edit_message_text("📞 Contact: @YourAdminUsername")
    elif data == "help":
        await query.edit_message_text("Use /help for usage instructions.")
    elif data == "admin":
        await query.edit_message_text("Admin tools: /users /feedstatus /broadcast")


# ------------------------------------------------------
# Application builder
# ------------------------------------------------------
def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CallbackQueryHandler(button_callback))
    return app


application = build_application()

if __name__ == "__main__":
    application.run_polling()
