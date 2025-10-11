import os
import re
import asyncio
import logging
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from sqlalchemy import text as _t
from db import get_session, get_or_create_user_by_tid
from ui_texts import welcome_full, help_footer
from utils_fx import to_usd, load_fx_rates

# ==========================================================
# Logging
# ==========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================================
# Main keyboard fallback (ίδιο layout με screenshots)
# ==========================================================
def main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+ Add Keywords", callback_data="act:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
        ],
        [
            InlineKeyboardButton("📨 Contact", callback_data="act:contact"),
            InlineKeyboardButton("🔥 Admin", callback_data="act:admin"),
        ],
    ])


# ==========================================================
# Start command — initializes and shows trial dates
# ==========================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from os import getenv
    days = int(getenv("TRIAL_DAYS", "10"))

    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)

        # Initialize trial_start and trial_end if missing
        s.execute(
            _t('UPDATE "user" SET trial_start = COALESCE(trial_start, NOW()) WHERE id=:id'),
            {"id": u.id},
        )
        s.execute(
            _t('UPDATE "user" SET trial_end = COALESCE(trial_end, NOW() + (:d || \' days\')::interval) WHERE id=:id'),
            {"id": u.id, "d": str(days)},
        )
        s.commit()

        row = s.execute(
            _t('SELECT trial_start, trial_end, license_until FROM "user" WHERE id=:id'),
            {"id": u.id},
        ).fetchone()

    # Welcome message
    await update.effective_chat.send_message(
        welcome_full(days),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=main_keyboard(is_admin_user(update.effective_user.id)),
    )

    # Display trial info block
    if row:
        ts, te, lic = row
        await update.effective_chat.send_message(
            f"<b>🧾 Your access</b>\n• Start: {ts}\n• Trial ends: {te} UTC\n• License until: {lic}",
            parse_mode=ParseMode.HTML,
        )


# ==========================================================
# Dummy admin check (προσαρμόζεται με την πραγματική σου λογική)
# ==========================================================
def is_admin_user(tid: int) -> bool:
    admins = os.getenv("ADMIN_IDS", "").split(",")
    return str(tid) in admins


# ==========================================================
# Example help command
# ==========================================================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_admin = is_admin_user(uid)
    text = (
        "Welcome to Freelancer Alert Bot!\n\n"
        "Use the menu below to manage your alerts and settings."
        + help_footer(24, admin=is_admin)
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ==========================================================
# Application builder
# ==========================================================
def build_application():
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    logger.info("✅ Application handlers registered.")
    return app


# ==========================================================
# For standalone debugging (optional)
# ==========================================================
if __name__ == "__main__":
    app = build_application()
    app.run_polling()
