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

try:
    from db import ensure_keyword_unique  # type: ignore
except Exception:
    def ensure_keyword_unique():
        logging.getLogger("bot").warning("ensure_keyword_unique() not found in db.py — skipping")

try:
    from db import list_keywords as _list_keywords  # type: ignore
except Exception:
    _list_keywords = None
try:
    from db import add_keywords as _add_keywords  # type: ignore
except Exception:
    _add_keywords = None
try:
    from db import delete_keyword as _delete_keyword  # type: ignore
except Exception:
    _delete_keyword = None
try:
    from db import clear_keywords as _clear_keywords  # type: ignore
except Exception:
    _clear_keywords = None

try:
    from ui_texts import HELP_EN, help_footer, welcome_full
except Exception:
    HELP_EN = "<b>Help</b>\nUse /addkeyword to start receiving job alerts."
    def help_footer(h:int)->str: return f"\n\nStats window: {h}h"
    def welcome_full(trial_days: int = 10) -> str:
        return f"<b>Welcome!</b> You have a {trial_days}-day trial. Use /addkeyword to begin."

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

def is_admin_user(telegram_id: int) -> bool:
    try:
        return int(telegram_id) in ADMIN_IDS
    except Exception:
        return False

# ---------- keyword fallbacks (schema-agnostic) ----------
from sqlalchemy import text as _t

def _kw_expr() -> str:
    return 'COALESCE(keyword, value)'

def list_keywords_safe(user_id: int) -> List[str]:
    try:
        if _list_keywords:
            return _list_keywords(user_id)  # type: ignore
    except Exception:
        log.exception("list_keywords (db) failed; fallback used")
    with get_session() as s:
        rows = s.execute(_t(f'SELECT {_kw_expr()} FROM "keyword" WHERE user_id=:uid ORDER BY id ASC'), {"uid": user_id}).fetchall()
        return [r[0] for r in rows if r and r[0]]

def add_keywords_safe(s, user_id: int, values: List[str]) -> int:
    try:
        if _add_keywords:
            return _add_keywords(s, user_id, values)  # type: ignore
    except Exception:
        log.exception("add_keywords (db) failed; fallback used")
    ins = 0
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        ex = s.execute(_t('SELECT 1 FROM "keyword" WHERE user_id=:u AND (keyword=:v OR value=:v) LIMIT 1'),
                       {"u": user_id, "v": v}).fetchone()
        if ex:
            continue
        s.execute(_t('INSERT INTO "keyword"(user_id, keyword, value) VALUES (:u, :v, :v)'),
                  {"u": user_id, "v": v})
        ins += 1
    if ins:
        s.commit()
    return ins

def delete_keyword_safe(s, user_id: int, value: str) -> bool:
    try:
        if _delete_keyword:
            return _delete_keyword(s, user_id, value)  # type: ignore
    except Exception:
        log.exception("delete_keyword (db) failed; fallback used")
    rc = s.execute(_t('DELETE FROM "keyword" WHERE user_id=:u AND (keyword=:v OR value=:v)'),
                   {"u": user_id, "v": value}).rowcount
    if rc:
        s.commit()
    return rc > 0

def clear_keywords_safe(s, user_id: int) -> int:
    try:
        if _clear_keywords:
            return _clear_keywords(s, user_id)  # type: ignore
    except Exception:
        log.exception("clear_keywords (db) failed; fallback used")
    rc = s.execute(_t('DELETE FROM "keyword" WHERE user_id=:u'), {"u": user_id}).rowcount
    if rc:
        s.commit()
    return int(rc or 0)

# ---------- UI helpers ----------
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
        return "<b>Welcome!</b>\nUse /addkeyword to add search keywords. Open the menu to explore settings."

# ---------- Commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            s.execute(text('UPDATE "user" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=:id'), {"id": u.id})
            s.execute(text('UPDATE "user" SET trial_end=COALESCE(trial_end, NOW() AT TIME ZONE \'UTC\') + INTERVAL :days WHERE id=:id').bindparams(days=f"{TRIAL_DAYS} days"), {"id": u.id})
            expiry = s.execute(text('SELECT COALESCE(license_until, trial_end) FROM "user" WHERE id=:id'), {"id": u.id}).scalar()
            s.commit()
        except Exception:
            log.exception("start_cmd: trial init failed (non-fatal)")
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

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.effective_chat.send_message(
        f"<b>User</b>\n• id: <code>{u.id}</code>\n• username: @{u.username if u.username else '-'}",
        parse_mode=ParseMode.HTML,
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords_safe(user.id)
    kw_str = ", ".join(kws) if kws else "(none)"
    await update.effective_chat.send_message(
        f"<b>My settings</b>\n• <b>Keywords:</b> {kw_str}\n\nUse /addkeyword, /delkeyword, /clearkeywords.",
        parse_mode=ParseMode.HTML,
    )

def _split_keywords(arg: str) -> List[str]:
    if not arg:
        return []
    raw = [x.strip() for x in arg.replace(";", ",").split(",")]
    return [x for x in raw if x]

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /addkeyword word1, word2, ...")
        return
    kws = _split_keywords(args)
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        n = add_keywords_safe(s, u.id, kws)
    await update.message.reply_text(f"Added {n} keyword(s).")

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /delkeyword word")
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        ok = delete_keyword_safe(s, u.id, args.strip())
    await update.message.reply_text("Deleted." if ok else "Not found.")

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        n = clear_keywords_safe(s, u.id)
    await update.message.reply_text(f"Cleared {n} keyword(s).")

# ---------- Self-test ----------
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
        f"  <b>🔎 Match:</b> <a href=\"{match_url}\">logo</a>\n"
        f"  <b>📝</b> {description}"
    )
    url = "https://www.peopleperhour.com/freelance-jobs/technology-programming/other/"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url), InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"), InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------- CallbackQuery handler for main menu ----------
async def cb_mainmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data if q else ""
    await q.answer()
    if data == "act:addkw":
        await q.message.reply_text("Send /addkeyword word1, word2, ...")
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        await q.message.reply_text("No saved items yet.")
    elif data == "act:contact":
        await q.message.reply_text("Contact admin: @your_username")
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await q.message.reply_text("Admin panel: /users, /grant <id> <days>, /block <id>, /unblock <id>, /feedstatus")
        else:
            await q.message.reply_text("You are not an admin.")
    else:
        await q.message.reply_text("Unknown action.")

# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    with get_session() as s:
        try:
            rows = s.execute(text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 200')).fetchall()
        except Exception:
            await update.message.reply_text("Unable to query users.")
            return
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = len(list_keywords_safe(uid))
        lines.append(f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end or '-'} | lic:{lic or '-'} | active:{'Y' if act else 'N'} | blocked:{'Y' if blk else 'N'}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}")
        return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours.")
        return
    await update.effective_chat.send_message("📊 Feed status (last %dh):\n%s" % (STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k, v in stats.items()])))

# ---------- Build app (no JobQueue to avoid warning) ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    app.add_handler(CallbackQueryHandler(cb_mainmenu))  # enables the buttons

    return app
