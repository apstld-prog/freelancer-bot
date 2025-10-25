import logging
import os
from datetime import datetime, timedelta
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from db import get_or_create_user_by_tid, get_user_keywords, add_keyword, delete_keyword, clear_keywords
from utils import format_job_message, fetch_demo_jobs

logger = logging.getLogger(__name__)

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)

# ------------------------------------------------------
# Layout Buttons
# ------------------------------------------------------
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="add_keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="help"),
            InlineKeyboardButton("💾 Saved", callback_data="saved"),
        ],
        [
            InlineKeyboardButton("📞 Contact", callback_data="contact"),
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
    user["trial_expiry"] = expiry

    text = (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial.</b>\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts.\n"
        f"<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "Use /help for instructions."
    )

    await update.message.reply_text(
        text, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML
    )


async def help_command(update: Update, context: CallbackContext):
    text = (
        "🎯 <b>Help / How it works</b>\n\n"
        "<b>Keywords</b>\n"
        "• Add: /addkeyword logo, lighting, sales\n"
        "• Remove: /delkeyword logo, sales\n"
        "• Clear all: /clearkeywords\n\n"
        "<b>Other</b>\n"
        "• Set countries: /setcountry US,UK or ALL\n"
        "• Save proposal: /setproposal <text>\n"
        "• Test card: /selftest\n\n"
        "🌍 <b>Platforms monitored:</b>\n"
        "• Global: Freelancer.com (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal, Codeable, YunoJuno, Worksome, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "👑 <b>Admin:</b>\n"
        "/users /grant <id> <days> /block <id> /unblock <id>\n"
        "/broadcast <text> /feedstatus"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def selftest(update: Update, context: CallbackContext):
    """Show sample job alerts from both platforms"""
    jobs = await fetch_demo_jobs()
    for job in jobs:
        msg, markup = format_job_message(job)
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=markup)


# ------------------------------------------------------
# Callback buttons
# ------------------------------------------------------
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "add_keywords":
        await query.edit_message_text("Use /addkeyword <words> to add keywords.")
    elif data == "settings":
        await query.edit_message_text("Settings coming soon.")
    elif data == "help":
        await query.edit_message_text("Use /help for full instructions.")
    elif data == "saved":
        await query.edit_message_text("Saved list is currently empty.")
    elif data == "contact":
        await query.edit_message_text("📞 Contact: @YourAdminUsername")
    elif data == "admin":
        await query.edit_message_text("🔥 Admin panel: /users /feedstatus /broadcast")


# ------------------------------------------------------
# Application setup
# ------------------------------------------------------
def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CallbackQueryHandler(button_callback))
    return app


application = build_application()

if __name__ == "__main__":
    application.run_polling()
