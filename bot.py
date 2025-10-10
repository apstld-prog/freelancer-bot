
from __future__ import annotations
import logging, urllib.parse
from datetime import datetime
from typing import List

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes
from sqlalchemy import text

from config import BOT_TOKEN, ADMIN_IDS, STATS_WINDOW_HOURS, TRIAL_DAYS
from db import get_session, ensure_schema, get_or_create_user_by_tid
from db_events import ensure_feed_events_schema, get_platform_stats
from db_saved import ensure_saved_schema, add_saved_job, list_saved_jobs
import ui_texts as ui

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

try:
    from db import ensure_keyword_unique  # type: ignore
except Exception:
    def ensure_keyword_unique():
        log.warning("ensure_keyword_unique() not found in db.py — skipping")

def is_admin_user(tid: int) -> bool:
    try:
        return int(tid) in ADMIN_IDS
    except Exception:
        return False

from sqlalchemy import text as _t

def _kwexpr() -> str:
    return 'COALESCE(keyword, value)'

def list_keywords_safe(user_id: int) -> List[str]:
    with get_session() as s:
        rows = s.execute(_t(f'SELECT {_kwexpr()} FROM "keyword" WHERE user_id=:u ORDER BY id ASC'), {"u": user_id}).fetchall()
        return [r[0] for r in rows if r and r[0]]

def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

# ===== Commands (layout preserved) =====
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            s.execute(_t("UPDATE \"user\" SET is_active=TRUE WHERE id=:id"), {"id": u.id})
            s.execute(_t("UPDATE \"user\" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE 'UTC') WHERE id=:id"), {"id": u.id})
            s.execute(_t("UPDATE \"user\" SET trial_end=COALESCE(trial_end, NOW() AT TIME ZONE 'UTC') + INTERVAL :days WHERE id=:id")
                      .bindparams(days=f"{TRIAL_DAYS} days"), {"id": u.id})
            s.commit()
        except Exception:
            log.exception("start init failed")
    await update.effective_chat.send_message(
        ui.welcome_card(trial_days=TRIAL_DAYS if isinstance(TRIAL_DAYS, int) else 10),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
        disable_web_page_preview=True
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(ui.help_card(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        row = s.execute(_t('SELECT is_active, is_blocked, trial_start, trial_end, license_until FROM "user" WHERE id=:id'), {"id": u.id}).fetchone()
    active = bool(row[0]) if row else False
    blocked = bool(row[1]) if row else False
    trial_start = row[2] if row else None
    trial_end = row[3] if row else None
    license_until = row[4] if row else None
    kws = ", ".join(list_keywords_safe(u.id)) or "(none)"
    countries = "ALL"  # unchanged (placeholder if you had country filters elsewhere)
    proposal = "(none)"
    await update.effective_chat.send_message(
        ui.mysettings_card(kws, countries, proposal, active, blocked, trial_start, trial_end, license_until),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Matches screenshot layout (Freelancer sample)
    job_title = "Email Signature from Existing Logo"
    budget_min = 10.0
    budget_max = 30.0
    source = "Freelancer"
    match_url = "https://www.freelancer.com/jobs/?keyword=logo"
    description = "Please duplicate and make an editable version of my existing email signature based on the logo file"
    job_text = (
        f"<b>{job_title}</b>\n"
        f"  <b>Budget:</b> {budget_min:.1f}–{budget_max:.1f}\n"
        f"  <b>Source:</b> {source}\n"
        f"  <b>🔎 Match:</b> <a href=\"{match_url}\">logo</a>\n"
        f"  <b>📝</b> {description}"
    )
    url = "https://www.freelancer.com/projects/"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Proposal", url=url),
        InlineKeyboardButton("🔗 Original", url=url)
    ],[
        InlineKeyboardButton("⭐ Save", callback_data="job:save|Email%20Signature|https%3A%2F%2Fwww.freelancer.com%2Fprojects%2F"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")
    ]])
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)

async def cb_mainmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = q.data if q else ""
    await q.answer()
    if data == "act:addkw":
        await q.message.reply_text("Use /addkeyword word1, word2")
    elif data == "act:settings":
        await whoami_cmd(update, context)
    elif data == "act:saved":
        with get_session() as s:
            user = get_or_create_user_by_tid(s, update.effective_user.id)
        rows = list_saved_jobs(user.id, 25)
        if not rows:
            await q.message.reply_text("No saved jobs yet."); return
        lines = ["<b>Saved jobs</b>"]
        for sid, title, url, desc, created in rows:
            lines.append(f"• <a href=\"{url or '#'}\">{title or '(no title)'} </a>")
        await q.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:contact":
        await q.message.reply_text("Contact: @your_username")
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await q.message.reply_text("Admin: /users, /feedstatus")
        else:
            await q.message.reply_text("You're not an admin.")
    else:
        await q.message.reply_text("Unknown action.")

async def cb_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = q.data or ""
    if data.startswith("job:save"):
        await q.answer("Saved ⭐", show_alert=False)
        try: await q.message.delete()
        except Exception: pass
    elif data == "job:delete":
        await q.answer("Deleted 🗑️", show_alert=False)
        try: await q.message.delete()
        except Exception: pass
    else:
        await q.answer("Unknown action", show_alert=False)

def build_application() -> Application:
    ensure_schema(); ensure_feed_events_schema(); ensure_saved_schema(); ensure_keyword_unique()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CallbackQueryHandler(cb_mainmenu, pattern="^(act:)"))
    app.add_handler(CallbackQueryHandler(cb_job, pattern="^job:"))
    return app
