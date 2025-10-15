import os
import logging
from sqlalchemy import text as _t

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Keep existing handlers exactly as in your project
from handlers_start import start_cmd
from handlers_help import help_cmd
from handlers_settings import feedstatus_cmd, selftest_cmd

# DB helpers (unchanged)
from db import get_session as _gs, get_or_create_user_by_tid

log = logging.getLogger(__name__)


# ======================================================================
# Save/Delete buttons handler (functional fix only, no UI changes)
# ======================================================================
async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles Save/Delete buttons for job cards.
    Save -> FK-safe insert using INTERNAL user.id, then delete the message.
    Delete -> delete the message (or clear buttons). No alerts required.
    """
    q = update.callback_query
    data = (q.data or "").strip()
    msg = q.message

    # Read original job link (if present) from existing inline keyboard buttons (no UI change)
    original_url = ""
    try:
        if msg and msg.reply_markup and msg.reply_markup.inline_keyboard:
            first_row = msg.reply_markup.inline_keyboard[0]
            # Prefer 2nd button URL if present, else fallback to 1st
            if len(first_row) > 1 and getattr(first_row[1], "url", None):
                original_url = first_row[1].url or ""
            elif len(first_row) >= 1 and getattr(first_row[0], "url", None):
                original_url = first_row[0].url or ""
    except Exception:
        original_url = ""

    # Derive a title from the card text (first <b>…</b> or first line)
    title = "Saved job"
    try:
        import re as _re
        text_html = msg.text_html or msg.text or ""
        m = _re.search(r"<b>([^<]+)</b>", text_html)
        if m:
            title = m.group(1).strip()[:255]
        else:
            first_line = (text_html.splitlines()[0] if text_html else "").strip()
            if first_line:
                title = first_line[:255]
    except Exception:
        pass

    # ======================
    # SAVE
    # ======================
    if data == "job:save":
        try:
            with _gs() as s:
                # ✅ Ensure user exists and use INTERNAL PK (not Telegram ID)
                uobj = get_or_create_user_by_tid(s, update.effective_user.id)
                internal_uid = uobj.id  # <-- this satisfies the FK saved_job.user_id -> user.id

                # Be tolerant to various legacy schemas (no UI change)
                s.execute(_t("""
                    CREATE TABLE IF NOT EXISTS saved_job (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL
                    )
                """))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS title TEXT"))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS url TEXT"))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS description TEXT"))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))

                # Avoid duplicate saves per user/title/url
                exists = s.execute(_t("""
                    SELECT 1 FROM saved_job
                    WHERE user_id=:u AND title=:t AND COALESCE(url,'')=COALESCE(:uurl,'')
                    LIMIT 1
                """), {"u": internal_uid, "t": title, "uurl": original_url}).scalar()

                if not exists:
                    # Try insert with created_at; if column default/exists differs, fall back gracefully
                    try:
                        s.execute(_t("""
                            INSERT INTO saved_job (user_id, title, url, description, created_at)
                            VALUES (:u, :t, :uurl, :d, NOW())
                        """), {"u": internal_uid, "t": title, "uurl": original_url or "", "d": ""})
                    except Exception:
                        s.execute(_t("""
                            INSERT INTO saved_job (user_id, title, url, description)
                            VALUES (:u, :t, :uurl, :d)
                        """), {"u": internal_uid, "t": title, "uurl": original_url or "", "d": ""})
                s.commit()
        except Exception as e:
            # We avoid user alerts per your spec; keep logs for diagnostics
            log.exception("job:save error: %s", e)

        # Delete the card message (or at least clear buttons)
        try:
            if msg:
                await msg.delete()
            else:
                raise Exception("no message to delete")
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

        # No UI change to alerts; keep as simple callback answer
        return await q.answer()

    # ======================
    # DELETE
    # ======================
    if data == "job:delete":
        try:
            if msg:
                await msg.delete()
            else:
                raise Exception("no message to delete")
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await q.answer()

    # Default
    await q.answer()


# ======================================================================
# Application factory (required by server.py) — unchanged structure
# ======================================================================
def build_application():
    """
    Factory required by server.py to initialize the Telegram bot.
    Do not change structure; keep handlers as in original setup.
    """
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands (unchanged)
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    application.add_handler(CommandHandler("selftest", selftest_cmd))
    application.add_handler(CommandHandler("help", help_cmd))

    # Buttons (Save/Delete)
    application.add_handler(CallbackQueryHandler(job_action_cb))

    return application
