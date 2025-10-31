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

def settings_text(keywords: List[str], countries: str|None, proposal_template: str|None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    def b(v: bool) -> str: return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00","Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00","Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00","Z")
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

# ---------- /start (PostgreSQL safe) ----------
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

# ---------- whoami ----------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML
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
        settings_text(
            kws,
            row["countries"],
            row["proposal_template"],
            row["trial_start"],
            row["trial_end"],
            row["license_until"],
            bool(row["is_active"]),
            bool(row["is_blocked"]),
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

# ---------- Keyword management ----------
def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        lp = p.lower()
        if lp not in seen:
            seen.add(lp)
            out.append(p)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    kws = _parse_keywords(" ".join(context.args))
    if not kws:
        await update.message.reply_text("No valid keywords provided.")
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    inserted = add_keywords(u.id, kws)
    current = list_keywords(u.id)
    msg = (
        f"✅ Added {inserted} new keyword(s)."
        if inserted > 0
        else "ℹ️ Those keywords already exist (no changes)."
    )
    await update.message.reply_text(
        msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
        parse_mode=ParseMode.HTML,
    )

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Delete keywords. Example:\n<code>/delkeyword logo, sales</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    removed = delete_keywords(u.id, kws)
    left = list_keywords(u.id)
    await update.message.reply_text(
        f"🗑 Removed {removed} keyword(s).\n\nCurrent keywords:\n• "
        + (", ".join(left) if left else "—"),
        parse_mode=ParseMode.HTML,
    )

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
                InlineKeyboardButton("❌ No", callback_data="kw:clear:no"),
            ]
        ]
    )
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
# ---------- Self-test ----------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        job_text = (
            "<b>Email Signature from Existing Logo</b>\n"
            "<b>Budget:</b> 10.0–30.0 USD\n"
            "<b>Source:</b> Freelancer\n"
            "<b>Match:</b> logo\n"
            "✏️ Please create an editable version of the email signature based on the provided logo.\n"
        )
        url = "https://www.freelancer.com/projects/sample"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal", url=url),
             InlineKeyboardButton("🔗 Original", url=url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
        ])
        await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.4)

        pph_text = (
            "<b>Logo Design for New Startup</b>\n"
            "<b>Budget:</b> 50.0–120.0 GBP (~$60–$145 USD)\n"
            "<b>Source:</b> PeoplePerHour\n"
            "<b>Match:</b> logo\n"
            "🎨 Create a modern, minimal logo for a UK startup. Provide vector files.\n"
        )
        pph_url = "https://www.peopleperhour.com/freelance-jobs/sample"
        pph_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal", url=pph_url),
             InlineKeyboardButton("🔗 Original", url=pph_url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
        ])
        await update.effective_chat.send_message(pph_text, parse_mode=ParseMode.HTML, reply_markup=pph_kb)
        ensure_feed_events_schema()
        record_event("freelancer")
        record_event("peopleperhour")
        log.info("selftest: recorded freelancer + peopleperhour")
    except Exception as e:
        log.exception("selftest failed: %s", e)

# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin."); return
    with get_session() as s:
        s.execute(text('SELECT id,telegram_id,trial_end,license_until,is_active,is_blocked FROM "user" ORDER BY id DESC LIMIT 200'))
        rows = s.fetchall()
    lines = ["<b>Users</b>"]
    for r in rows:
        uid,tid = r["id"], r["telegram_id"]
        trial_end,lic = r["trial_end"], r["license_until"]
        act,blk = r["is_active"], r["is_blocked"]
        kwc = count_keywords(uid)
        lines.append(f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end} | lic:{lic} | A:{'✅' if act else '❌'} B:{'✅' if blk else '❌'}")
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}"); return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    await update.effective_chat.send_message("📊 Feed status (last %dh):\n%s" %
        (STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k,v in stats.items()])))

async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args)<2:
        await update.effective_chat.send_message("Usage: /grant <id> <days>"); return
    tid=int(context.args[0]); days=int(context.args[1])
    until=datetime.now(timezone.utc)+timedelta(days=days)
    with get_session() as s:
        s.execute(text('UPDATE "user" SET license_until=:dt WHERE telegram_id=:tid'),{"dt":until,"tid":tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tid}.")
    try: await context.bot.send_message(chat_id=tid,text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception: pass

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(update.message.text.split())<2:
        await update.effective_chat.send_message("Usage: /block <id>"); return
    tid=int(update.message.text.split()[1])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=TRUE WHERE telegram_id=:tid'),{"tid":tid}); s.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tid}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(update.message.text.split())<2:
        await update.effective_chat.send_message("Usage: /unblock <id>"); return
    tid=int(update.message.text.split()[1])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=FALSE WHERE telegram_id=:tid'),{"tid":tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tid}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args:
        await update.effective_chat.send_message("Usage: /broadcast <text>"); return
    txt=" ".join(context.args)
    with get_session() as s:
        s.execute(text('SELECT telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'))
        rows=s.fetchall()
        ids=[r["telegram_id"] for r in rows]
    for tid in ids:
        try: await context.bot.send_message(chat_id=tid,text=txt,parse_mode=ParseMode.HTML)
        except Exception: pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {len(ids)} users.")
# ---------- Expiry reminders + scheduler ----------
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now=datetime.now(timezone.utc); soon=now+timedelta(hours=24)
    with get_session() as s:
        s.execute(text('SELECT telegram_id,COALESCE(license_until,trial_end) AS expiry FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'))
        rows=s.fetchall()
    for r in rows:
        tid,expiry=r["telegram_id"],r["expiry"]
        if not expiry: continue
        if getattr(expiry,"tzinfo",None) is None: expiry=expiry.replace(tzinfo=timezone.utc)
        if now<expiry<=soon:
            try:
                hours_left=int((expiry-now).total_seconds()//3600)
                await context.bot.send_message(chat_id=tid,
                    text=f"⏰ Reminder: your access expires in about {hours_left} hours (on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).")
            except Exception: pass

# ---------- Build Application ----------
def build_application() -> Application:
    ensure_schema(); ensure_feed_events_schema(); ensure_keyword_unique()
    app=ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("feetstatus", feedstatus_cmd))

    # Scheduler
    if JobQueue is not None:
        jq=app.job_queue or JobQueue()
        if app.job_queue is None: jq.set_application(app)
        jq.run_repeating(notify_expiring_job,interval=3600,first=60)
        log.info("Scheduler: JobQueue active")
    else:
        log.warning("JobQueue unavailable — expiry loop skipped")
    return app
