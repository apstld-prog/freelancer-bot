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

# keep these imports exactly as in your project
from handlers_start import start_cmd
from handlers_help import help_cmd
from handlers_settings import feedstatus_cmd, selftest_cmd

from db import get_session as _gs, get_or_create_user_by_tid

log = logging.getLogger(__name__)


async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Save/Delete buttons on job cards.
    - Save: FK-safe insert using INTERNAL user.id (from `user` table), then delete the message.
    - Delete: delete message (or clear buttons). No UI alerts.
    """
    q = update.callback_query
    data = (q.data or "").strip()
    msg = q.message

    # read original job link from inline keyboard (unchanged UI)
    original_url = ""
    try:
        if msg and msg.reply_markup and msg.reply_markup.inline_keyboard:
            row = msg.reply_markup.inline_keyboard[0]
            if len(row) > 1 and getattr(row[1], "url", None):
                original_url = row[1].url or ""
            elif len(row) >= 1 and getattr(row[0], "url", None):
                original_url = row[0].url or ""
    except Exception:
        original_url = ""

    # infer a title from text
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

    if data == "job:save":
        try:
            with _gs() as s:
                # ✅ ensure user exists and use INTERNAL PK (NOT telegram id)
                uobj = get_or_create_user_by_tid(s, update.effective_user.id)
                internal_uid = uobj.id

                # be tolerant to legacy schemas
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

                # avoid duplicates per (user,title,url)
                exists = s.execute(_t("""
                    SELECT 1 FROM saved_job
                    WHERE user_id=:u AND title=:t AND COALESCE(url,'')=COALESCE(:uurl,'')
                    LIMIT 1
                """), {"u": internal_uid, "t": title, "uurl": original_url}).scalar()

                if not exists:
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
            log.exception("job:save error: %s", e)

        # delete the card (fallback: clear buttons)
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

    await q.answer()


def build_application():
    """
    Required by server.py — unchanged structure.
    """
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    application.add_handler(CommandHandler("selftest", selftest_cmd))
    application.add_handler(CommandHandler("help", help_cmd))

    application.add_handler(CallbackQueryHandler(job_action_cb))

    return application
