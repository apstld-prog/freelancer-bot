# bot.py — EN-only, robust admin + keyword system, corrected /start for PostgreSQL
import os, logging, asyncio, re
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)
try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore
from sqlalchemy import text
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats, record_event
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- Admin helpers ----------
def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE'))
            ids = [r["telegram_id"] for r in s.fetchall()]
        return {int(x) for x in ids if x}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

# ---------- UI ----------
def main_menu_kb(is_admin: bool=False) -> InlineKeyboardMarkup:
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

HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>Keywords</b>\n"
    "• Add: <code>/addkeyword logo, lighting, sales</code>\n"
    "• Remove: <code>/delkeyword logo, sales</code>\n"
    "• Clear all: <code>/clearkeywords</code>\n\n"
    "<b>Other</b>\n"
    "• Set countries: <code>/setcountry US,UK</code> or <code>ALL</code>\n"
    "• Save proposal: <code>/setproposal &lt;text&gt;</code>\n"
    "• Test card: <code>/selftest</code>\n"
)
def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: Freelancer.com (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin:</b> <code>/users</code> <code>/grant &lt;id&gt; &lt;days&gt;</code> "
        "<code>/block &lt;id&gt;</code> <code>/unblock &lt;id&gt;</code> <code>/broadcast &lt;text&gt;</code> "
        "<code>/feedstatus</code> (alias <code>/feetstatus</code>)\n"
        "<i>Link previews are disabled for this message.</i>\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts."
        f"{extra}\n\nUse <code>/help</code> for instructions.\n"
    )

# ---------- /start ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(
            'UPDATE "user" SET trial_start = COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id = %(id)s;',
            {"id": u.id},
        )
        s.execute(
            'UPDATE "user" SET trial_end = COALESCE(trial_end, (NOW() AT TIME ZONE \'UTC\') + make_interval(days => %(days)s)) WHERE id = %(id)s;',
            {"id": u.id, "days": TRIAL_DAYS},
        )
        s.execute(
            'SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id = %(id)s;',
            {"id": u.id},
        )
        row = s.fetchone()
        expiry = row["expiry"] if row else None
        s.commit()

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

# ---------- My Settings ----------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        s.execute(
            text(
                'SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked '
                'FROM "user" WHERE id=:id'
            ),
            {"id": u.id},
        )
        row = s.fetchone()
    await update.message.reply_text(
        f"<b>🛠 Your Settings</b>\n• Keywords: {', '.join(kws) if kws else '(none)'}",
        parse_mode=ParseMode.HTML,
    )

# ---------- Keyword Management ----------
async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
         InlineKeyboardButton("❌ No", callback_data="kw:clear:no")],
    ])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

# ---------- FIXED: Callback for clear confirm ----------
async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not (q.data or "").startswith("kw:clear:"):
        return await q.answer()
    choice = q.data.split(":")[-1]
    if choice == "no":
        await q.message.edit_text("❌ Cancelled. Keywords unchanged.")
        return await q.answer()
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
    count = clear_keywords(u.id)
    await q.message.edit_text(f"🗑 Cleared {count} keyword(s).")
    await q.answer()
# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    with get_session() as s:
        s.execute(text('SELECT id,telegram_id,trial_end,license_until,is_active,is_blocked FROM "user" ORDER BY id DESC LIMIT 200'))
        rows = s.fetchall()
    txt = ["<b>Users</b>"]
    for r in rows:
        txt.append(f"• {r['telegram_id']} | A:{'✅' if r['is_active'] else '❌'} B:{'✅' if r['is_blocked'] else '❌'}")
    await update.message.reply_text("\n".join(txt), parse_mode=ParseMode.HTML)

# ---------- Menu action callback ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "act:addkw":
        await addkeyword_cmd(update, context)
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data.startswith("act:admin"):
        await users_cmd(update, context)
    else:
        await q.message.reply_text("Unknown action.")

# ---------- Build app ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear:(yes|no)$"))

    log.info("✅ Application fully built and ready.")
    return app
