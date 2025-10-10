# bot.py — EN-only code, preserves existing structure & UI
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
)
from sqlalchemy import text

# Project modules
from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    STATS_WINDOW_HOURS,
    TRIAL_DAYS,
)
from db import (
    get_session,
    ensure_schema,
    # do not import is_admin_user from db — define locally
    get_or_create_user_by_tid,
    list_keywords,
    count_keywords,
    add_keywords,
    delete_keyword,
    clear_keywords,
)
from db_events import ensure_feed_events_schema, get_platform_stats

# Try to import ensure_keyword_unique; if missing, use no-op
try:
    from db import ensure_keyword_unique  # type: ignore
except Exception:
    def ensure_keyword_unique():
        logging.getLogger("bot").warning("ensure_keyword_unique() not found in db.py — skipping")

# UI texts
try:
    from ui_texts import HELP_EN, help_footer, welcome_full
except Exception:
    HELP_EN = "<b>Help</b>\nUse /addkeyword to start receiving job alerts."
    def help_footer(h:int)->str: return f"\n\nStats window: {h}h"
    def welcome_full(trial_days: int = 10) -> str:
        return f"<b>Welcome!</b> You have a {trial_days}-day trial. Use /addkeyword to begin."

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

# Local admin check (avoids missing db.is_admin_user)
def is_admin_user(telegram_id: int) -> bool:
    try:
        return int(telegram_id) in ADMIN_IDS
    except Exception:
        return False

# ---------------- UI helpers ----------------
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
        ],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

def welcome_text(expiry: Optional[datetime]) -> str:
    try:
        return welcome_full(trial_days=TRIAL_DAYS if isinstance(TRIAL_DAYS, int) else 10)
    except Exception:
        return (
            "<b>Welcome!</b>\n"
            "Use <code>/addkeyword</code> to add search keywords and get curated job alerts.\n"
            "Open the menu to explore settings and saved items."
        )

# ---------------- Commands ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            s.execute(
                text('UPDATE "user" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=:id'),
                {"id": u.id},
            )
            s.execute(
                text('UPDATE "user" SET trial_end=COALESCE(trial_end, NOW() AT TIME ZONE \'UTC\') + INTERVAL :days WHERE id=:id')
                .bindparams(days=f"{TRIAL_DAYS} days"),
                {"id": u.id},
            )
            expiry = s.execute(
                text('SELECT COALESCE(license_until, trial_end) FROM "user" WHERE id=:id'),
                {"id": u.id},
            ).scalar()
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
        kws = list_keywords(user.id)
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
    if not kws:
        await update.message.reply_text("No keywords provided.")
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            n = add_keywords(s, u.id, kws)
        except Exception:
            log.exception("addkeyword failed")
            n = 0
    await update.message.reply_text(f"Added {n} keyword(s).")

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /delkeyword word")
        return
    kw = args.strip()
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            ok = delete_keyword(s, u.id, kw)
        except Exception:
            log.exception("delkeyword failed")
            ok = False
    await update.message.reply_text("Deleted." if ok else "Not found.")

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            n = clear_keywords(s, u.id)
        except Exception:
            log.exception("clearkeywords failed")
            n = 0
    await update.message.reply_text(f"Cleared {n} keyword(s).")

# ---------------- Self-test card (PeoplePerHour style) ----------------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_title = "Email Signature from Existing Logo"
    budget_min = 10.0
    budget_max = 30.0
    source = "PeoplePerHour"
    match_url = "https://www.peopleperhour.com/freelance-jobs?q=logo"
    description = (
        "Please duplicate and make an editable version of my existing email signature based on the logo file"
    )

    job_text = (
        f"<b>{job_title}</b>\n"
        f"  <b>Budget:</b> {budget_min:.1f}–{budget_max:.1f}\n"
        f"  <b>Source:</b> {source}\n"
        f"  <b>🔎 Match:</b> <a href=\"{match_url}\">logo</a>\n"
        f"  <b>📝</b> {description}"
    )

    url = "https://www.peopleperhour.com/freelance-jobs/technology-programming/other/"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 Proposal", url=url), InlineKeyboardButton("🔗 Original", url=url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"), InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
        ]
    )

    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------- Admin commands ----------------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    with get_session() as s:
        try:
            rows = s.execute(
                text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 200')
            ).fetchall()
        except Exception:
            await update.message.reply_text("Unable to query users.")
            return

    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        try:
            kwc = count_keywords(uid)
        except Exception:
            kwc = 0
        lines.append(
            f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end or '-'} | lic:{lic or '-'} | active:{'Y' if act else 'N'} | blocked:{'Y' if blk else 'N'}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    await update.message.reply_text("Grant logic not implemented in this file (kept as in your base).")

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    await update.message.reply_text("Block logic not implemented in this file (kept as in your base).")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    await update.message.reply_text("Unblock logic not implemented in this file (kept as in your base).")

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
    await update.effective_chat.send_message(
        "📊 Feed status (last %dh):\n%s"
        % (STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k, v in stats.items()])),
    )

# ---------------- Build Application ----------------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    try:
        jq = app.job_queue or JobQueue()
        if app.job_queue is None:
            jq.set_application(app)
        logging.getLogger("bot").info("Scheduler: JobQueue ready")
    except Exception:
        logging.getLogger("bot").exception("JobQueue setup failed (non-fatal)")

    return app
