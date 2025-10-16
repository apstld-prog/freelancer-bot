# -*- coding: utf-8 -*-
# (Αρχείο bot.py όπως στο backup σου, με μία μόνο αλλαγή στο block act:saved)

# --- Saved list (κρατάει το format του worker) ---
if data == "act:saved":
    try:
        from sqlalchemy import text as _t
        from db import get_session as _gs
        from db import get_or_create_user_by_tid as _get_user

        uid = update.effective_user.id
        with _gs() as s:
            uobj = _get_user(s, uid)
            db_user_id = uobj.id

            rows = s.execute(
                _t("SELECT id, title, url, COALESCE(description,'') "
                   "FROM saved_job WHERE user_id=:uid_db "
                   "ORDER BY saved_at DESC LIMIT 10"),
                {"uid_db": db_user_id}
            ).fetchall()

        if not rows:
            await q.message.reply_text("Saved list: (empty)")
            await q.answer()
            return

        for rid, t, u, d in rows:
            title_txt = (t or '').strip() or '(no title)'
            body_txt = (d or '').strip()

            card = f"<b>{title_txt}</b>" + (f"\n{body_txt}" if body_txt else "")

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Proposal", url=u or ""),
                 InlineKeyboardButton("🔗 Original", url=u or "")],
                [InlineKeyboardButton("🗑️ Delete", callback_data=f"saved:del:{rid}")]
            ])

            try:
                await q.message.chat.send_message(
                    card,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                    disable_web_page_preview=True
                )
            except Exception:
                await q.message.reply_text(
                    card,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                    disable_web_page_preview=True
                )

        await q.answer()
        return

    except Exception:
        await q.answer()
        return
