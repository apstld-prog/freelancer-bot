# utils.py
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Literal
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

# ------------------------
# Trial settings
# ------------------------
DEFAULT_TRIAL_DAYS: int = 10

# ------------------------
# Basic utilities
# ------------------------
def now_utc() -> datetime:
    """Επιστρέφει τρέχουσα ώρα σε UTC (aware)."""
    return datetime.now(timezone.utc)


def _uid_field() -> Literal["telegram_id"]:
    """
    Το όνομα του πεδίου-κλειδιού χρήστη όπως είναι στο User model.
    Αν στο μέλλον αλλάξει, προσαρμόζουμε εδώ για να μη σπάσουν imports.
    """
    return "telegram_id"


# ------------------------
# Telegram bot send utility
# ------------------------
logger = logging.getLogger("utils")

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None


async def send_job_to_user(chat_id: int, job: dict):
    """
    Στέλνει αγγελία σε χρήστη στο Telegram με σωστή μορφοποίηση και κουμπιά.
    """
    if not bot:
        logger.error("[send_job_to_user] No Telegram bot token found.")
        return

    try:
        title = job.get("title", "Untitled job")
        desc = job.get("description", "")
        platform = job.get("platform", "Unknown")
        budget = job.get("budget", "N/A")
        keyword = job.get("keyword", "")

        # Δημιουργία κύριου μηνύματος
        text = f"🧩 <b>{platform}</b>\n\n" \
               f"<b>{title}</b>\n" \
               f"{desc}\n\n" \
               f"💰 <b>Budget:</b> {budget}\n"

        if keyword:
            text += f"🔑 <b>Keyword:</b> {keyword}\n"

        # Inline buttons
        url = job.get("affiliate_url") or job.get("url") or job.get("original_url")
        buttons = []
        if url:
            buttons.append([InlineKeyboardButton("🔗 View Job", url=url)])

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,
            reply_markup=reply_markup,
        )
        logger.info(f"[send_job_to_user] Sent job to {chat_id}")

    except Exception as e:
        logger.error(f"[send_job_to_user] Error sending job to {chat_id}: {e}")
