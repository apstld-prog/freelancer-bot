
from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler,
    ContextTypes,
)
from sqlalchemy import text

from config import BOT_TOKEN, ADMIN_IDS, STATS_WINDOW_HOURS, TRIAL_DAYS
from db import get_session, ensure_schema, get_or_create_user_by_tid
from db_events import ensure_feed_events_schema, get_platform_stats

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

# Optional helpers
try:
    from db import ensure_keyword_unique  # type: ignore
except Exception:
    def ensure_keyword_unique():
        log.warning("ensure_keyword_unique() not found in db.py — skipping")

# UI texts
try:
    from ui_texts import HELP_EN, help_footer, welcome_full
except Exception:
    HELP_EN = "<b>Help</b>\nUse /addkeyword to start receiving job alerts."
    def help_footer(h:int)->str: return f"\n\nStats window: {h}h"
    def welcome_full(trial_days: int = 10) -> str:
        return f"<b>Welcome!</b> You have a {trial_days}-day trial. Use /addkeyword to begin."

def is_admin_user(tid: int) -> bool:
    try:
        return int(tid) in ADMIN_IDS
    except Exception:
        return False

# -------- Keyword helpers (schema-agnostic) --------
from sqlalchemy import text as _t

def _kwexpr() -> str:
    return 'COALESCE(keyword, value)'

def list_keywords_safe(user_id: int) -> List[str]:
    with get_session() as s:
        rows = s.execute(_t(f'SELECT {_kwexpr()} FROM "keyword" WHERE user_id=:u ORDER BY id ASC'), {"u": user_id}).fetchall()
        return [r[0] for r in rows if r and r[0]]

def add_keywords_safe(user_id: int, values: List[str]) -> (int, List[str], List[str]):
    added, skipped = [], []
    if not values: return 0, added, skipped
    with get_session() as s:
        for v in values:
            vv = (v or "").strip()
            if not vv:
                continue
            ex = s.execute(_t('SELECT 1 FROM "keyword" WHERE user_id=:u AND (keyword=:v OR value=:v) LIMIT 1'),
                           {"u": user_id, "v": vv}).fetchone()
            if ex:
                skipped.append(vv)
                continue
            s.execute(_t('INSERT INTO "keyword"(user_id, keyword, value) VALUES (:u, :v, :v)'),
                     {"u": user_id, "v": vv})
            added.append(vv)
        if added:
            s.commit()
    return len(added), added, skipped

def delete_keyword_safe(user_id: int, value: str) -> bool:
    with get_session() as s:
        rc = s.execute(_t('DELETE FROM "keyword" WHERE user_id=:u AND (keyword=:v OR value=:v)'),
                       {"u": user_id, "v": value}).rowcount
        if rc:
            s.commit()
    return rc > 0

def clear_keywords_safe(user_id: int) -> int:
    with get_session() as s:
        rc = s.execute(_t('DELETE FROM "keyword" WHERE user_id=:u'), {"u": user_id}).rowcount
        if rc:
            s.commit()
    return int(rc or 0)

# -------- UI helpers --------
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

def welcome_text(expiry: Optional[datetime]) -> str:
    try:
        return welcome_full(trial_days=TRIAL_DAYS if isinstance(TRIAL_DAYS, int) else 10)
    except Exception:
        return "<b>Welcome!</b>\nUse /addkeyword to add search keywords."

# -------- Commands --------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            # FIXED: clean SQL strings (no bad escapes)
            s.execute(_t("UPDATE \"user\" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE 'UTC') WHERE id=:id"), {"id": u.id})
            s.execute(_t("UPDATE \"user\" SET trial_end=COALESCE(trial_end, NOW() AT TIME ZONE 'UTC') + INTERVAL :days WHERE id=:id")
                      .bindparams(days=f"{TRIAL_DAYS} days"), {"id": u.id})
            expiry = s.execute(_t('SELECT COALESCE(license_until, trial_end) FROM "user" WHERE id=:id'), {"id": u.id}).scalar()
            s.commit()
        except Exception:
            logging.getLogger("bot").exception("start_cmd: trial init failed")
            expiry = None

    await update.effective_chat.send_message(
        welcome_text(expiry if isinstance(expiry, datetime) else None),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    kws = list_keywords_safe(user.id)
    kw_str = ", ".join(kws) if kws else "(none)"
    await update.effective_chat.send_message(
        f"<b>My settings</b>\n• <b>Keywords:</b> {kw_str}\n\nΧρήση: /addkeyword λέξη1, λέξη2 (ελληνικά/αγγλικά).",
        parse_mode=ParseMode.HTML,
    )

def _parse_kw_args(text: str) -> List[str]:
    if not text:
        return []
    txt = text.replace(";", ",").replace("  ", " ")
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    if not parts:
        parts = [p.strip() for p in txt.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.effective_message.text or ""
    raw = raw.partition(" ")[2]
    kws = _parse_kw_args(raw)
    if not kws:
        await update.message.reply_text("Χρήση: /addkeyword λέξη1, λέξη2")
        return
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    n, added, skipped = add_keywords_safe(user.id, kws)
    msg = f"✅ Προστέθηκαν: {', '.join(added)}" if added else "—"
    if skipped:
        msg += f"\n↪️ Ήδη υπήρχαν: {', '.join(skipped)}"
    await update.message.reply_text(msg)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.effective_message.text or ""
    arg = raw.partition(" ")[2].strip()
    if not arg:
        await update.message.reply_text("Χρήση: /delkeyword λέξη")
        return
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    ok = delete_keyword_safe(user.id, arg)
    await update.message.reply_text("Διαγράφηκε." if ok else "Δεν βρέθηκε.")

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    n = clear_keywords_safe(user.id)
    await update.message.reply_text(f"Καθαρίστηκαν {n} keywords.")

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_title = "Email Signature from Existing Logo"
    budget_min = 10.0
    budget_max = 30.0
    source = "PeoplePerHour"
    match_url = "https://www.peopleperhour.com/freelance-jobs?q=logo"
    description = "Please duplicate and make an editable version of my existing email signature based on the logo file"
    job_text = (
        f"<b>{job_title}</b>\n"
        f"  <b>Budget:</b> {budget_min:.1f}–{budget_max:.1f}\n"
        f"  <b>Source:</b> {source}\n"
        f"  <b>🔎 Match:</b> <a href=\\"{match_url}\\">logo</a>\n"
        f"  <b>📝</b> {description}"
    )
    url = "https://www.peopleperhour.com/freelance-jobs/technology-programming/other/"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Proposal", url=url),
        InlineKeyboardButton("🔗 Original", url=url)
    ],[
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")
    ]])
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def cb_mainmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = q.data if q else ""
    await q.answer()
    if data == "act:addkw":
        await q.message.reply_text("Στείλε: /addkeyword λέξη1, λέξη2")
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        await q.message.reply_text("Δεν έχεις αποθηκεύσει αγγελίες ακόμη.")
    elif data == "act:contact":
        await q.message.reply_text("Επικοινωνία: @your_username")
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await q.message.reply_text("Admin: /users, /feedstatus")
        else:
            await q.message.reply_text("Δεν είσαι admin.")
    else:
        await q.message.reply_text("Άγνωστη ενέργεια.")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("Δεν είσαι admin."); return
    with get_session() as s:
        rows = s.execute(text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 200')).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = len(list_keywords_safe(uid))
        lines.append(f"• <a href=\\"tg://user?id={tid}\\">{tid}</a> — kw:{kwc} | trial:{trial_end or '-'} | lic:{lic or '-'} | active:{'Y' if act else 'N'} | blocked:{'Y' if blk else 'N'}")
    await update.message.reply_text("\\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    await update.effective_chat.send_message("📊 Feed status (last %dh):\n%s" % (STATS_WINDOW_HOURS, "\\n".join([f"• {k}: {v}" for k, v in stats.items()])))

def build_application() -> Application:
    ensure_schema(); ensure_feed_events_schema(); ensure_keyword_unique()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("addkw", addkeyword_cmd))           # alias
    app.add_handler(CommandHandler("keywords", mysettings_cmd))        # alias
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    # Buttons
    app.add_handler(CallbackQueryHandler(cb_mainmenu))
    return app
