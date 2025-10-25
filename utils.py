# utils.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
import os
import httpx
import logging

# Πόσες μέρες trial δίνουμε by default
DEFAULT_TRIAL_DAYS: int = 10

def now_utc() -> datetime:
    """Επιστρέφει τρέχουσα ώρα σε UTC (aware)."""
    return datetime.now(timezone.utc)

def _uid_field() -> Literal["telegram_id"]:
    """
    Το όνομα του πεδίου-κλειδιού χρήστη όπως είναι στο User model.
    Αν στο μέλλον αλλάξει, προσαρμόζουμε εδώ για να μη σπάσουν imports.
    """
    return "telegram_id"

# --------------------------------------------------------------
# Add Telegram send_job_to_user helper
# --------------------------------------------------------------

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
logger = logging.getLogger("utils")

async def send_job_to_user(user_id: int, job: dict) -> bool:
    """
    Sends a single job message to the Telegram user.
    job: dict containing title, description, url, budget_display, keyword, posted_at, etc.
    """
    try:
        title = job.get("title", "Untitled")
        desc = job.get("description", "")
        budget = job.get("budget_display") or job.get("budget") or "N/A"
        keyword = job.get("keyword") or job.get("match") or "N/A"
        url = job.get("url") or job.get("original_url") or "N/A"
        posted = job.get("posted_at") or "N/A"

        text = (
            f"📄 <b>{title}</b>\n"
            f"🔑 Keyword: {keyword}\n"
            f"💰 Budget: {budget}\n"
            f"🕓 Posted: {posted}\n\n"
            f"{desc[:500]}...\n\n"
            f"<a href=\"{url}\">🔗 View project</a>"
        )

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json={
                    "chat_id": user_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
            )
            r.raise_for_status()

        logger.info(f"[send_job_to_user] Sent job → {user_id} ({title[:40]}...)")
        return True

    except Exception as e:
        logger.warning(f"[send_job_to_user] Error sending to {user_id}: {e}")
        return False
