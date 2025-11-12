import logging
from telegram import Update
from telegram.ext import ContextTypes

from db import get_or_create_user_by_tid
from config import TRIAL_DAYS

log = logging.getLogger("handlers_start")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    get_or_create_user_by_tid(uid)

    text = (
        "👋 *Welcome to Freelancer Alert Bot!*\n\n"
        f"🎁 You have a *{TRIAL_DAYS}-day free trial*.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n"
        "Use /help to see how it works.\n"
        "________________________________________\n"
        "⭐ *Features*\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped Proposal & Original links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑️ Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)"
    )

    # Reply only with text — no inline buttons
    await update.message.reply_text(text, parse_mode="Markdown")
