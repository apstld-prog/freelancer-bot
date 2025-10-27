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
ADMIN_ELEVATE_SECRET = os.getenv("ADMIN_ELEVATE_SECRET", "")


# ---------- Admin helpers ----------
def get_db_admin_ids() -> Set[int]:
    """Read admins from user table."""
    try:
        with get_session() as s:
            ids = [r[0] for r in s.execute(
                text('SELECT telegram_id FROM user WHERE is_admin=TRUE')
            ).fetchall()]
        return {int(x) for x in ids if x}
    except Exception:
        return set()


def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()


def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()


# ---------- UI ----------
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("Settings ⚙️", callback_data="act:settings")],
        [InlineKeyboardButton("Help 🆘", callback_data="act:help"),
         InlineKeyboardButton("Saved 💾", callback_data="act:saved")],
        [InlineKeyboardButton("Contact 📨", callback_data="act:contact")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("Admin 🔥", callback_data="act:admin")])
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
        "• Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin:</b> <code>/users</code> <code>/grant &lt;id&gt; &lt;days&gt;</code> "
        "<code>/block &lt;id&gt;</code> <code>/unblock &lt;id&gt;</code> <code>/broadcast &lt;text&gt;</code> "
        "<code>/feedstatus</code>\n"
        "<i>Link previews are disabled for this message.</i>\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial/access ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts."
        f"{extra}\n\nUse <code>/help</code> for instructions.\n"
    )
def settings_text(keywords: List[str], countries: str | None, proposal_template: str | None,
                  started_at, trial_until, access_until, active: bool, blocked: bool) -> str:
    def b(v: bool) -> str: return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = started_at.isoformat().replace("+00:00", "Z") if started_at else "—"
    te = trial_until.isoformat().replace("+00:00", "Z") if trial_until else "—"
    lic = "None" if not access_until else access_until.isoformat().replace("+00:00", "Z")
    return (
        "<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {k}\n"
        f"• <b>Countries:</b> {c}\n"
        f"• <b>Proposal template:</b> {pt}\n\n"
        f"<b>●</b> Start date: {ts}\n"
        f"<b>●</b> Trial ends: {te} UTC\n"
        f"<b>🔑</b> License until: {lic}\n"
        f"<b>✅ Active:</b> {b(active)}    <b>⛔ Blocked:</b> {b(blocked)}\n\n"
        "<b>🛰 Platforms monitored:</b> Global & GR boards.\n"
        "<i>For extension, contact the admin.</i>"
    )


# ---------- Commands ----------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)

        s.execute(text(
            "UPDATE user SET started_at=COALESCE(started_at, NOW() AT TIME ZONE 'UTC') WHERE id=:id"
        ), {"id": u.id})

        s.execute(
            text("UPDATE user SET trial_until=COALESCE(trial_until, (NOW() AT TIME ZONE 'UTC') + INTERVAL ':days days') WHERE id=:id")
            .bindparams(days=TRIAL_DAYS),
            {"id": u.id},
        )

        expiry = s.execute(text(
            "SELECT COALESCE(access_until, trial_until) FROM user WHERE id=:id"
        ), {"id": u.id}).scalar()

        s.commit()

    await update.effective_chat.send_message(
        welcome_text(expiry if isinstance(expiry, datetime) else None),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )

    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(text(
            "SELECT countries, proposal_template, started_at, trial_until, access_until, is_active, is_blocked "
            "FROM user WHERE id=:id"
        ), {"id": u.id}).fetchone()
    await update.message.reply_text(
        settings_text(kws, row[0], row[1], row[2], row[3], row[4], bool(row[5]), bool(row[6])),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT telegram_id, COALESCE(access_until, trial_until)
            FROM user
            WHERE is_active=TRUE AND is_blocked=FALSE
        """)).fetchall()
    for tid, expiry in rows:
        if not expiry:
            continue
        if getattr(expiry, "tzinfo", None) is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            try:
                hours_left = int((expiry - now).total_seconds() // 3600)
                await context.bot.send_message(chat_id=tid,
                    text=f"Reminder: your access expires in about {hours_left} hours (on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).")
            except Exception:
                pass


def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))

    try:
        if JobQueue is not None:
            jq = app.job_queue or JobQueue()
            if app.job_queue is None:
                jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)
            log.info("Scheduler: JobQueue active")
        else:
            raise RuntimeError("no jobqueue")
    except Exception:
        app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(asyncio.sleep(3600))
        log.info("Scheduler: fallback loop")
    return app
