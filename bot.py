import os
import logging
import re
import sys
import telegram
from typing import List, Dict

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed, JobSent

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "")
ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-bot")
logger.info(f"Python runtime: {sys.version}")
logger.info(f"python-telegram-bot version: {getattr(telegram, '__version__', 'unknown')}")

_SPLIT_RE = re.compile(r"[,\n]+")

# --------- Platforms list ---------
PLATFORM_LIST = [
    "🌍 *Global Freelancing*: Freelancer.com, PeoplePerHour (UK), Malt (FR/EU), Workana (ES/EU/LatAm), Fiverr Affiliates, Upwork",
    "🇬🇷 *Greek Job Boards*: JobFind.gr, Skywalker.gr, Kariera.gr",
]

WELCOME = "👋 *Welcome to Freelancer Alerts Bot!*"
HELP = "📖 *Help...* (όπως το είχαμε πριν)"


# ---------------- Helpers ----------------
def is_admin(user_id: int) -> bool:
    return ADMIN_ID and user_id == ADMIN_ID


# ---------------- Admin Commands ----------------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = (
        "🙋 *WhoAmI*\n\n"
        f"🆔 Your Telegram ID: `{user.id}`\n"
        f"👤 Name: {user.first_name or ''} {user.last_name or ''}\n"
        f"🔗 Username: @{user.username if user.username else '(none)'}"
    )
    await update.effective_message.reply_text(txt, parse_mode="Markdown")


async def adminstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        keyword_count = db.query(Keyword).count()
        jobs_sent = db.query(JobSent).count()
        jobs_saved = db.query(JobSaved).count()
        jobs_dismissed = db.query(JobDismissed).count()

        text = (
            "📊 *Bot Statistics*\n\n"
            f"👥 Users: {user_count}\n"
            f"🔑 Keywords: {keyword_count}\n"
            f"📤 Jobs sent: {jobs_sent}\n"
            f"⭐ Jobs saved: {jobs_saved}\n"
            f"🙈 Jobs dismissed: {jobs_dismissed}\n"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")
    finally:
        db.close()


async def adminusers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    db = SessionLocal()
    try:
        users = db.query(User).all()
        lines = ["👥 *Registered Users*:"]
        for u in users:
            lines.append(f"• {u.telegram_id} | Countries: {u.countries or 'ALL'} | Keywords: {len(u.keywords)}")
        text = "\n".join(lines)
        await update.effective_message.reply_text(text, parse_mode="Markdown")
    finally:
        db.close()


# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Admin & diagnostic commands
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("adminstats", adminstats_cmd))
    app.add_handler(CommandHandler("adminusers", adminusers_cmd))

    # (βάλε εδώ και τα υπόλοιπα commands: start, help, mysettings, keywords, platforms, setcountry κλπ)

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
