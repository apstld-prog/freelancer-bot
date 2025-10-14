# bot.py — EN-only, add via /addkeyword only, robust keywords, admin panel, selftest
# (Only job_action_cb updated for Save/Delete reliability)
import os, logging, asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore
from sqlalchemy import text
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats, record_event
from db_keywords import list_keywords, add_keywords, count_keywords, ensure_keyword_unique, delete_keywords, clear_keywords

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
ADMIN_ELEVATE_SECRET = os.getenv("ADMIN_ELEVATE_SECRET", "")

# -------------------------------------------------------------------------
# (Everything above unchanged — only the callback function updated)
# -------------------------------------------------------------------------

async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Save/Delete buttons for job cards."""
    q = update.callback_query
    data = (q.data or "").strip()
    msg = q.message
    user_id = update.effective_user.id

    # Extract Original URL
    original_url = ""
    try:
        if msg and msg.reply_markup and msg.reply_markup.inline_keyboard:
            first_row = msg.reply_markup.inline_keyboard[0]
            if len(first_row) > 1 and getattr(first_row[1], "url", None):
                original_url = first_row[1].url or ""
            elif len(first_row) >= 1 and getattr(first_row[0], "url", None):
                original_url = first_row[0].url or ""
    except Exception:
        pass

    # Extract title
    title = ""
    try:
        import re as _re
        text_html = msg.text_html or msg.text or ""
        m = _re.search(r"<b>([^<]+)</b>", text_html)
        if m:
            title = m.group(1).strip()
        if not title:
            title = (text_html.splitlines()[0] if text_html else "")[:200]
    except Exception:
        title = "Saved job"

    # --- SAVE JOB ---
    if data == "job:save":
        try:
            from sqlalchemy import text as _t
            from db import get_session as _gs
            with _gs() as s:
                s.execute(_t("""
                    CREATE TABLE IF NOT EXISTS saved_job (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT,
                        description TEXT,
                        saved_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
                    )
                """))
                # Avoid duplicates
                exists = s.execute(_t(
                    "SELECT 1 FROM saved_job WHERE user_id=:u AND title=:t AND url=:uurl LIMIT 1"
                ), {"u": user_id, "t": title, "uurl": original_url}).scalar()
                if not exists:
                    s.execute(_t(
                        "INSERT INTO saved_job (user_id, title, url, description) VALUES (:u, :t, :uurl, :d)"
                    ), {"u": user_id, "t": title, "uurl": original_url or "", "d": ""})
                s.commit()
        except Exception as e:
            log.exception(f"job:save error: {e}")

        # Try deleting or clearing buttons
        try:
            if msg:
                await msg.delete()
            else:
                raise Exception("no msg")
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await q.answer()

    # --- DELETE JOB ---
    if data == "job:delete":
        try:
            if msg:
                await msg.delete()
            else:
                raise Exception("no msg")
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await q.answer()

    await q.answer()
