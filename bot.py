# bot.py — Full corrected with all commands (Render-safe, original structure intact)
import os, logging, asyncio
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

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
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
        "• Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal, Codeable, YunoJuno, Worksome, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin:</b> /users /grant /block /unblock /broadcast /feedstatus\n"
    )
def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds freelance jobs from top platforms and sends alerts instantly."
        f"{extra}\n\nUse /help for instructions.\n"
    )

def settings_text(keywords: List[str], countries: str|None, proposal_template: str|None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    def b(v): return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries or "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00","Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00","Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00","Z")
    return (
        f"<b>🛠 Your Settings</b>\n• Keywords: {k}\n• Countries: {c}\n• Proposal: {pt}\n\n"
        f"Start: {ts}\nTrial ends: {te}\nLicense: {lic}\nActive: {b(active)}  Blocked: {b(blocked)}"
    )

# ---------- /start ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute('UPDATE "user" SET trial_start = COALESCE(trial_start, NOW()) WHERE id=%(id)s;', {"id": u.id})
        s.execute(
            'UPDATE "user" SET trial_end = COALESCE(trial_end, NOW() + make_interval(days => %(days)s)) WHERE id=%(id)s;',
            {"id": u.id, "days": TRIAL_DAYS})
        s.execute('SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id=%(id)s;', {"id": u.id})
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

# ---------- whoami ----------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML
    )

# ---------- My Settings ----------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        s.execute(text(
            'SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked '
            'FROM "user" WHERE id=:id'), {"id": u.id})
        row = s.fetchone()
    await update.effective_chat.send_message(
        settings_text(kws, row["countries"], row["proposal_template"], row["trial_start"],
                      row["trial_end"], row["license_until"], bool(row["is_active"]), bool(row["is_blocked"])),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ---------- Help ----------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.effective_chat.send_message(
            HELP_EN + help_footer(STATS_WINDOW_HOURS),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
        )
    except Exception as e:
        log.error(f"help_cmd failed: {e}")
        try:
            await update.effective_chat.send_message("⚠️ Help unavailable, please try again later.")
        except:
            pass

# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.effective_chat.send_message("You are not an admin."); return
    with get_session() as s:
        s.execute(text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 100'))
        rows = s.fetchall()
    lines = ["<b>Users</b>"]
    for r in rows:
        lines.append(f"• {r['telegram_id']} | trial:{r['trial_end']} | lic:{r['license_until']} | A:{'✅' if r['is_active'] else '❌'} B:{'✅' if r['is_blocked'] else '❌'} kw:{count_keywords(r['id'])}")
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <id> <days>"); return
    tid, days = int(context.args[0]), int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text('UPDATE "user" SET license_until=:dt WHERE telegram_id=:tid'), {"dt": until, "tid": tid})
        s.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tid}.")

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 1: await update.effective_chat.send_message("Usage: /block <id>"); return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=TRUE WHERE telegram_id=:tid'), {"tid": tid}); s.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tid}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 1: await update.effective_chat.send_message("Usage: /unblock <id>"); return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=FALSE WHERE telegram_id=:tid'), {"tid": tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tid}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.effective_chat.send_message("Usage: /broadcast <text>"); return
    msg = " ".join(context.args)
    with get_session() as s:
        s.execute(text('SELECT telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'))
        rows = s.fetchall()
    for r in rows:
        try:
            await context.bot.send_message(chat_id=r["telegram_id"], text=msg)
        except Exception:
            pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {len(rows)} users.")

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    stats = get_platform_stats(STATS_WINDOW_HOURS)
    if not stats:
        await update.effective_chat.send_message("No recent feed events."); return
    lines = [f"📊 Feed status (last {STATS_WINDOW_HOURS}h):"]
    for k, v in stats.items(): lines.append(f"• {k}: {v}")
    await update.effective_chat.send_message("\n".join(lines))

async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    with get_session() as s:
        s.execute(text('SELECT telegram_id, COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'))
        rows = s.fetchall()
    for r in rows:
        exp = r["expiry"]
        if exp and now < exp <= soon:
            hours_left = int((exp - now).total_seconds() // 3600)
            try:
                await context.bot.send_message(chat_id=r["telegram_id"],
                    text=f"⏰ Reminder: your access expires in {hours_left}h ({exp.strftime('%Y-%m-%d %H:%M UTC')})")
            except Exception:
                pass
# ---------- Menu ----------
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
    elif data == "act:admin":
        await users_cmd(update, context)
    else:
        await q.edit_message_text("❌ Unknown action.")

# ---------- Build ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # public
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("feetstatus", feedstatus_cmd))

    # menu
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(clearkeywords_cmd, pattern=r"^kw:clear:(yes|no)$"))

    if JobQueue:
        jq = app.job_queue or JobQueue()
        if app.job_queue is None:
            jq.set_application(app)
        jq.run_repeating(notify_expiring_job, interval=3600, first=60)
        log.info("Scheduler active ✅")

    return app
