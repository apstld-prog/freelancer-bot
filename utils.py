
# utils.py — unified utilities for sending jobs & helpers
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot

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
# Time utils
# ------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def time_ago(created_iso: Optional[str]) -> str:
    """Return human-readable time difference from ISO string."""
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

# ------------------------
# Currency helper (thin wrapper) — optional import, fallback safe
# ------------------------
def convert_to_usd(amount, currency) -> str:
    try:
        from currency_usd import to_usd_amount  # our helper in your project
    except Exception:
        return "N/A"
    try:
        if amount is None:
            return "N/A"
        return str(to_usd_amount(float(str(amount).split()[0]), (currency or "USD").upper()))
    except Exception:
        return "N/A"

# ------------------------
# Send Telegram message
# ------------------------
async def send_job_to_user(app, chat_id: int, message: str, job: dict):
    """
    Sends a job listing to a Telegram user with inline buttons.
    - app is accepted for API compatibility (not used here).
    - chat_id MUST be the Telegram chat/user id (e.g., 5254014824), not the internal DB id.
    """
    if not bot:
        logger.error("[send_job_to_user] No bot token set.")
        return

    # Guard: chat_id should look like a real Telegram id; if not, just log.
    if int(chat_id) < 100000000:
        logger.warning("[send_job_to_user] Skipping because chat_id looks like a DB id, not Telegram id: %s", chat_id)
        return

    try:
        platform = job.get("platform", "Unknown")
        url = job.get("affiliate_url") or job.get("url") or job.get("original_url")
        keyword = job.get("matched_keyword") or job.get("keyword") or "N/A"

        buttons = []
        if url:
            buttons.append([InlineKeyboardButton("🔗 View Job", url=url)])
        buttons.append([
            InlineKeyboardButton("💾 Save", callback_data="job:save"),
            InlineKeyboardButton("🗑 Delete", callback_data="job:delete"),
        ])

        markup = InlineKeyboardMarkup(buttons)

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=False,
        )
        logger.info("[send_job_to_user] Sent %s job to %s (kw=%s)", platform, chat_id, keyword)
    except Exception as e:
        logger.error("[send_job_to_user] Error sending job to %s: %s", chat_id, e)
