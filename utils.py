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
# Time utility — added back
# ------------------------
def time_ago(dt) -> str:
    """Υπολογίζει φιλική μορφή χρόνου (π.χ. '2 hours ago')."""
    if not dt:
        return "N/A"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return "N/A"
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)} minutes ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)} hours ago"
    else:
        return f"{int(seconds // 86400)} days ago"


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

        text = f"🧩 <b>{platform}</b>\n\n" \
               f"<b>{title}</b>\n" \
               f"{desc}\n\n" \
               f"💰 <b>Budget:</b> {budget}\n"

        if keyword:
            text += f"🔑 <b>Keyword:</b> {keyword}\n"

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

# --- Add this at the END of utils.py ---
def get_or_create_user_by_tid(s, telegram_id):
    """
    Compatibility helper for bot.py — ensures user exists by Telegram ID.
    Uses existing get_or_create_user() if available.
    """
    try:
        # Αν υπάρχει η κανονική συνάρτηση, τη χρησιμοποιούμε
        return get_or_create_user(s, telegram_id)
    except NameError:
        # Fallback χειροκίνητης δημιουργίας, αν λείπει η get_or_create_user
        from db import User
        u = s.execute(
            text("SELECT * FROM users WHERE telegram_id=:tid"),
            {"tid": telegram_id}
        ).fetchone()
        if u:
            return u
        s.execute(
            text("INSERT INTO users (telegram_id, created_at, is_active) "
                 "VALUES (:tid, NOW() AT TIME ZONE 'UTC', TRUE)"),
            {"tid": telegram_id}
        )
        s.commit()
        return s.execute(
            text("SELECT * FROM users WHERE telegram_id=:tid"),
            {"tid": telegram_id}
        ).fetchone()
