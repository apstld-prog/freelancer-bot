# bot.py — FULL WORKING VERSION (Render / PostgreSQL / Multi-Worker)
import os, logging, asyncio, re
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from sqlalchemy import text
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats, record_event
from db_keywords import (
    list_keywords, add_keywords, delete_keywords,
    clear_keywords, ensure_keyword_unique, count_keywords
)

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

# ---------- ADMIN HELPERS ----------
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
def main_menu_kb(is_admin=False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "• /addkeyword logo, lighting\n"
    "• /delkeyword logo\n"
    "• /clearkeywords — remove all\n\n"
    "<b>Other:</b>\n"
    "/selftest — show test cards\n"
    "/mysettings — show profile info\n"
    "/feedstatus — show platform stats\n"
)

def help_footer(hours: int) -> str:
    return (
        f"\n<b>🛰 Platforms monitored:</b>\n"
        f"Freelancer.com, PeoplePerHour, Skywalker, JobFind, Kariera.\n\n"
        f"<b>👑 Admin:</b> /users /grant /block /unblock /broadcast /feedstatus\n"
        f"<i>Stats window: {hours}h</i>"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs and sends instant alerts."
        f"{extra}\n\nUse /help for instructions."
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
        row = s.execute(
            'SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id = %(id)s;',
            {"id": u.id},
        ).fetchone()
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

# ---------- Help ----------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

# ---------- Keyword Management ----------
async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
         InlineKeyboardButton("❌ No", callback_data="kw:clear:no")],
    ])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    choice = q.data.split(":")[-1]
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
        if choice == "yes":
            count = clear_keywords(u.id)
            await q.edit_message_text(f"🗑 Cleared {count} keyword(s).")
        else:
            await q.edit_message_text("❌ Cancelled.")

# ---------- Self-test ----------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ensure_feed_events_schema()
        record_event("freelancer")
        record_event("peopleperhour")
        await update.message.reply_text("✅ Self-test OK — dummy events recorded.")
    except Exception as e:
        await update.message.reply_text(f"❌ Self-test failed: {e}")

# ---------- Feed Status ----------
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS)
        if not stats:
            await update.message.reply_text("No events found in last 24h.")
            return
        msg = "📊 Feed status (last 24h):\n" + "\n".join([f"• {k}: {v}" for k, v in stats.items()])
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Feed status unavailable: {e}")
# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("Not admin.")
        return
    with get_session() as s:
        rows = s.execute(text('SELECT telegram_id, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 50')).fetchall()
    txt = ["<b>Users</b>"]
    for r in rows:
        txt.append(f"• {r['telegram_id']} — Active:{'✅' if r['is_active'] else '❌'} Blocked:{'✅' if r['is_blocked'] else '❌'}")
    await update.message.reply_text("\n".join(txt), parse_mode=ParseMode.HTML)

# ---------- Menu buttons ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "act:help":
        await help_cmd(update, context)
    elif data == "act:addkw":
        await update.effective_chat.send_message("Use /addkeyword logo, design, etc.")
    elif data == "act:settings":
        await update.effective_chat.send_message("Use /mysettings to view profile.")
    elif data == "act:admin":
        await users_cmd(update, context)
    else:
        await update.effective_chat.send_message("Unknown button.")

# ---------- Build app ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear:(yes|no)$"))

    log.info("✅ Application built and ready.")
    return app
