from telegram import Update
from telegram.ext import ContextTypes

async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles Save/Delete buttons for job cards.
    Save -> insert into DB using INTERNAL user.id (FK-safe), then delete the message.
    Delete -> delete the message (or strip buttons). No alerts to the user.
    """
    q = update.callback_query
    data = (q.data or "").strip()
    msg = q.message

    # --- Extract Original URL from inline keyboard ---
    original_url = ""
    try:
        if msg and msg.reply_markup and msg.reply_markup.inline_keyboard:
            first_row = msg.reply_markup.inline_keyboard[0]
            if len(first_row) > 1 and getattr(first_row[1], "url", None):
                original_url = first_row[1].url or ""
            elif len(first_row) >= 1 and getattr(first_row[0], "url", None):
                original_url = first_row[0].url or ""
    except Exception:
        original_url = ""

    # --- Extract a title from first bold line or first line ---
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

    # === SAVE BUTTON ===
    if data == "job:save":
        try:
            from sqlalchemy import text as _t
            from db import get_session as _gs, get_or_create_user_by_tid

            with _gs() as s:
                # ✅ Ensure user exists in DB and get internal PK (not Telegram ID)
                uobj = get_or_create_user_by_tid(s, update.effective_user.id)
                internal_uid = uobj.id

                # ✅ Ensure required columns exist
                s.execute(_t("""
                    CREATE TABLE IF NOT EXISTS saved_job (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        saved_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
                    )
                """))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS title TEXT"))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS url TEXT"))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS description TEXT"))
                s.execute(_t("ALTER TABLE saved_job ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')"))

                # ✅ Avoid duplicates
                exists = s.execute(_t("""
                    SELECT 1 FROM saved_job
                    WHERE user_id=:u AND title=:t AND COALESCE(url,'')=COALESCE(:uurl,'')
                    LIMIT 1
                """), {"u": internal_uid, "t": title, "uurl": original_url}).scalar()

                if not exists:
                    s.execute(_t("""
                        INSERT INTO saved_job (user_id, title, url, description)
                        VALUES (:u, :t, :uurl, :d)
                    """), {
                        "u": internal_uid,
                        "t": title,
                        "uurl": original_url or "",
                        "d": ""
                    })
                s.commit()
        except Exception as e:
            s.rollback()
            log.exception("job:save error: %s", e)

        # Delete message or clear buttons
        try:
            if msg:
                await msg.delete()
            else:
                raise Exception("no message")
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await q.answer("Saved ✅", show_alert=False)

    # === DELETE BUTTON ===
    if data == "job:delete":
        try:
            if msg:
                await msg.delete()
            else:
                raise Exception("no message")
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await q.answer()

    await q.answer()
