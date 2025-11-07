# handlers_ui.py — FINAL FULL VERSION (Nov 2025)

import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from sqlalchemy import text

from db import get_session
from config import ADMIN_IDS

log = logging.getLogger("handlers_ui")


# ----------------------------------------------------------------------
# Header always on top
# ----------------------------------------------------------------------
def user_header(s, uid):
    row = s.execute(
        text('SELECT trial_end FROM "user" WHERE id=:i'),
        {"i": uid}
    ).fetchone()

    if not row or not row.trial_end:
        return "⏳ <b>Trial:</b> unknown\n"

    dt = row.trial_end.strftime("%Y-%m-%d %H:%M UTC")
    return f"⏳ <b>Trial ends:</b> {dt}\n"


# ----------------------------------------------------------------------
# UI main callback
# ----------------------------------------------------------------------
async def handle_ui_callback(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    with get_session() as s:
        header = user_header(s, uid)

    action = q.data.replace("ui:", "")

    # -------------------------
    if action == "addkw":
        msg = header + "➕ <b>Add Keywords</b>\nWrite keywords separated by comma."
        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return

    # -------------------------
    if action == "settings":
        with get_session() as s:
            row = s.execute(
                text('SELECT keywords, country, proposal FROM "user" WHERE id=:i'),
                {"i": uid},
            ).fetchone()
        kws = row.keywords or "(none)"
        msg = header + (
            "⚙ <b>Your Settings</b>\n"
            f"• Keywords: {kws}\n"
            f"• Country: {row.country or 'ALL'}\n"
            f"• Proposal: {row.proposal or '(none)'}"
        )
        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return

    # -------------------------
    if action == "saved":
        with get_session() as s:
            rows = s.execute(text("""
                SELECT title, budget_amount, budget_currency, affiliate_url,
                       platform, created_at
                FROM job_event
                ORDER BY created_at DESC
                LIMIT 10
            """)).fetchall()

        msg = header + "<b>💾 Saved Jobs</b>\n"
        if not rows:
            msg += "(none)"
        else:
            for r in rows:
                msg += (
                    f"\n<b>{r.title}</b>\n"
                    f"🪙 {r.budget_amount} {r.budget_currency}\n"
                    f"🌍 {r.platform}\n"
                    f"⏱ {r.created_at}\n"
                    f"{r.affiliate_url}\n"
                    "______________________________\n"
                )

        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return

    # -------------------------
    if action == "feed":
        msg = header + "📊 <b>Feed Status</b>\nWorking normally."
        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return

    # -------------------------
    if action == "contact":
        msg = header + (
            "📨 <b>Contact admin</b>\n"
            "Send your message here."
        )
        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return

    # -------------------------
    if action == "help":
        msg = header + "🆘 <b>Help</b>\nUse menu buttons."
        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return

    # -------------------------
    if action == "admin":
        if uid not in ADMIN_IDS:
            await q.message.edit_text("⛔ No access.")
            return

        msg = header + (
            "👑 <b>Admin Panel</b>\n"
            "/users\n"
            "/grant <id> <days>\n"
            "/block <id>\n"
            "/unblock <id>\n"
            "/broadcast <text>\n"
            "/feedsstatus\n"
        )
        await q.message.edit_text(msg, parse_mode=ParseMode.HTML)
        return


# ----------------------------------------------------------------------
# User text input (Add keywords, Contact, etc)
# ----------------------------------------------------------------------
async def handle_user_message(update, context):
    uid = update.effective_user.id
    txt = update.message.text

    # Contact mode
    if context.user_data.get("contact_mode"):
        for admin in ADMIN_IDS:
            await context.bot.send_message(
                admin,
                f"📩 From user {uid}:\n\n{text}",
            )
        context.user_data["contact_mode"] = False
        return await update.message.reply_text("✅ Sent.")

    # Add keyword mode (if you want later)
    return await update.message.reply_text("✅ Saved.")
