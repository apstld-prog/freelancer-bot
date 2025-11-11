# bot.py — EN-only, add via /addkeyword only, robust keywords, admin panel, selftest
import os, logging, asyncio, re
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore

from sqlalchemy import text

from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats
from db_events import record_event
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
ADMIN_ELEVATE_SECRET = os.getenv("ADMIN_ELEVATE_SECRET", "")

def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            ids = [r[0] for r in s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()]
        return {int(x) for x in ids if x}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

def main_menu_kb(is_admin: bool=False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🟩 Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("📘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact", callback_data="act:contact")],
    ]
    if is_admin: kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
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

def welcome_block(trial_days: int = TRIAL_DAYS) -> str:
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n"
        f"🎁 You have a <b>{trial_days}-day free trial.</b>\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n"
        "Use /help to see how it works.\n"
        "________________________________________\n"
        "🟩 <b>Keywords</b>  ⚙️ <b>Settings</b>\n"
        "📘 <b>Help</b>  💾 <b>Saved</b>\n"
        "📞 <b>Contact</b>\n"
        "🔥 <b>Admin</b>\n"
        "________________________________________\n"
        "✨ <b>Features</b>\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped Proposal & Original links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑️ Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)\n"
    )

def admin_contact_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{user_id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{user_id}")],
        [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{user_id}:30"),
         InlineKeyboardButton("+90d", callback_data=f"adm:grant:{user_id}:90"),
         InlineKeyboardButton("+180d", callback_data=f"adm:grant:{user_id}:180"),
         InlineKeyboardButton("+365d", callback_data=f"adm:grant:{user_id}:365")],
    ])

def pair_admin_user(app: Application, admin_id: int, user_id: int) -> None:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    pairs["user_to_admin"][user_id] = admin_id
    pairs["admin_to_user"][admin_id] = user_id

def get_paired_admin(app: Application, user_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["user_to_admin"].get(user_id)

def get_paired_user(app: Application, admin_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["admin_to_user"].get(admin_id)

def unpair(app: Application, admin_id: Optional[int]=None, user_id: Optional[int]=None):
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    if admin_id is not None:
        uid = pairs["admin_to_user"].pop(admin_id, None)
        if uid is not None: pairs["user_to_admin"].pop(uid, None)
    if user_id is not None:
        aid = pairs["user_to_admin"].pop(user_id, None)
        if aid is not None: pairs["admin_to_user"].pop(aid, None)

def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        lp = p.lower()
        if lp not in seen:
            seen.add(lp); out.append(p)
    return out

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)

        s.execute(
            text('UPDATE "user" SET trial_start = COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=:id'),
            {"id": u.id}
        )

        s.execute(
            text('UPDATE "user" SET trial_end = COALESCE(trial_end, (NOW() AT TIME ZONE \'UTC\') + (:days * INTERVAL \'1 day\')) WHERE id=:id'),
        ).bindparams(days=TRIAL_DAYS)

        s.commit()

    await update.effective_chat.send_message(
        welcome_block(TRIAL_DAYS),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
        disable_web_page_preview=True,
    )
