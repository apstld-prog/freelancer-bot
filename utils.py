# ======================================================
# utils.py — unified utilities for sending jobs & helpers
# ======================================================
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot
from utils_fx import to_usd

logger = logging.getLogger("utils")

# ------------------------
# Telegram bot setup
# ------------------------
BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# ------------------------
# Time and currency utils
# ------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def time_ago(created_iso: Optional[str]) -> str:
    """Return human-readable time difference."""
    try:
        dt = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        delta = now_utc() - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins} minutes ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours} hours ago"
        days = hours // 24
        return f"{days} days ago"
    except Exception:
        return "unknown"

def convert_to_usd(amount: str, currency: str) -> str:
    try:
        return str(to_usd(float(str(amount).split()[0]), currency))
    except Exception:
        return "N/A"

# ------------------------
# Send Telegram message
# ------------------------
async def send_job_to_user(app, chat_id: int, message: str, job: dict):
    """
    Sends a job listing to Telegram user with inline buttons.
    Compatible with workers (expects app, chat_id, message, job).
    """
    if not bot:
        logger.error("[send_job_to_user] No bot token found.")
        return

    try:
        platform = job.get("platform", "Unknown")
        url = job.get("affiliate_url") or job.get("url") or job.get("original_url")
        keyword = job.get("keyword") or "N/A"

        buttons = []
        if url:
            buttons.append([InlineKeyboardButton("🔗 View Job", url=url)])
        buttons.append([
            InlineKeyboardButton("💾 Save", callback_data="job:save"),
            InlineKeyboardButton("🗑 Delete", callback_data="job:delete")
        ])

        markup = InlineKeyboardMarkup(buttons)

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=False,
        )
        logger.info(f"[send_job_to_user] Sent {platform} job to {chat_id} (kw={keyword})")

    except Exception as e:
        logger.error(f"[send_job_to_user] Error sending job to {chat_id}: {e}")
