import os
import sys
import re
import logging
from typing import List, Dict

import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed, JobSent, AppLock

# ------------ Config ------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "")
ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-bot")
logger.info(f"python-telegram-bot version: {getattr(telegram, '__version__', 'unknown')}")

_SPLIT_RE = re.compile(r"[,\n]+")

# --------- Platforms ---------
PLATFORM_LIST = [
    "🌍 *Global Freelancing*: Freelancer.com, PeoplePerHour (UK), Malt (FR/EU), Workana (ES/EU/LatAm), Fiverr Affiliates, Upwork",
    "🇬🇷 *Greek Job Boards*: JobFind.gr, Skywalker.gr, Kariera.gr",
]

WELCOME = (
    "👋 *Welcome to Freelancer Alerts Bot!*\n\n"
    "Get real-time job alerts based on your keywords and country filters.\n\n"
    "👉 Use the menu below or commands to configure your settings."
)

HELP = (
    "📖 *Help / How it works*\n\n"
    "1️⃣ Add keywords with `/addkeyword python, telegram`\n"
    "2️⃣ View your keywords with `/keywords` or `/listkeywords`\n"
    "3️⃣ Delete one keyword with `/delkeyword <kw>`\n"
    "4️⃣ Clear all keywords with `/clearkeywords`\n"
    "5️⃣ Set your countries with `/setcountry US,UK` (or `ALL`)\n"
    "6️⃣ Save a proposal template with `/setproposal <text>`\n"
    "   Placeholders: {job_title}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budget_time}, {portfolio}, {name}\n"
    "7️⃣ When a job arrives you can:\n"
    "   • ⭐ Save it\n"
    "   • 🙈 Dismiss it\n"
    "   • 💼 Proposal → *direct affiliate link to job*\n"
    "   • 🔗 Original → *same affiliate-wrapped job link*\n\n"
    "⚙️ `/mysettings` to check filters.\n"
    "🧪 `/selftest` for a test job.\n"
    "🌍 `/platforms [CC]` to see platforms by country (e.g. `/platforms GR`).\n\n"
    "📡 *Platforms currently supported:*\n" + "\n".join(PLATFORM_LIST)
)

# ------------ Helpers ------------
def is_admin(user_id: int) -> bool:
    return ADMIN_ID and user_id == ADMIN_ID

# ------------ Commands ------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(WELCOME, reply_markup=main_menu_markup(), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP, reply_markup=main_menu_markup(), parse_mode="Markdown")

async def adminhelp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = (
        "🛡 *Admin Commands*\n\n"
        "• `/adminstats` – Bot statistics (users, keywords, jobs sent/saved/dismissed)\n"
        "• `/adminusers` – List all registered users with filters\n"
        "• `/whoami` – Show your Telegram ID\n"
    )
    await update.effective_message.reply_text(txt, parse_mode="Markdown")

# ------------ Menu ------------
def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add Keywords", callback_data="menu:add"),
                InlineKeyboardButton("🛠 Settings", callback_data="menu:settings"),
            ],
            [InlineKeyboardButton("📖 Help", callback_data="menu:help")],
        ]
    )

# ------------ Main ------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("platforms", lambda u, c: u.effective_message.reply_text("Platforms command...")))
    app.add_handler(CommandHandler("mysettings", lambda u, c: u.effective_message.reply_text("Mysettings...")))

    # Admin-only
    app.add_handler(CommandHandler("adminhelp", adminhelp_cmd))
    app.add_handler(CommandHandler("adminstats", lambda u, c: u.effective_message.reply_text("Adminstats...")))
    app.add_handler(CommandHandler("adminusers", lambda u, c: u.effective_message.reply_text("Adminusers...")))
    app.add_handler(CommandHandler("whoami", lambda u, c: u.effective_message.reply_text("Whoami...")))

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
