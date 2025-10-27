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
    try:
        with get_session() as s:
            ids = [r[0] for r in s.execute(
                text('SELECT telegram_id FROM users WHERE is_admin=TRUE')
            ).fetchall()]
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

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial/access ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts."
        f"{extra}\n\nUse <code>/help</code> for instructions.\n"
    )

# ---------- SAFE PATCHED start_cmd ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resilient /start: never crashes even if DB fails."""
    expiry = None
    try:
        with get_session() as s:
            u = get_or_create_user_by_tid(s, update.effective_user.id)
            s.execute(text(
                "UPDATE users SET started_at=COALESCE(started_at, NOW() AT TIME ZONE 'UTC') WHERE id=:id"
            ), {"id": u.id})
            s.execute(
                text("UPDATE users SET trial_until=COALESCE(trial_until, (NOW() AT TIME ZONE 'UTC') + INTERVAL ':days days') WHERE id=:id")
                .bindparams(days=TRIAL_DAYS),
                {"id": u.id},
            )
            expiry = s.execute(text(
                "SELECT COALESCE(access_until, trial_until) FROM users WHERE id=:id"
            ), {"id": u.id}).scalar()
            s.commit()
    except Exception as e:
        log.exception("⚠️ start_cmd fallback due to DB error: %s", e)
    try:
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
    except Exception as e:
        log.exception("⚠️ start_cmd send_message failed: %s", e)
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(text(
            "SELECT countries, proposal_template, started_at, trial_until, access_until, is_active, is_blocked "
            "FROM users WHERE id=:id"
        ), {"id": u.id}).fetchone()
    await update.message.reply_text(
        f"<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {', '.join(kws) if kws else '(none)'}\n"
        f"• <b>Countries:</b> {row[0] or 'ALL'}\n"
        f"• <b>Proposal template:</b> {'(saved)' if row[1] else '(none)'}\n\n"
        f"<b>●</b> Start date: {row[2]}\n"
        f"<b>●</b> Trial ends: {row[3]}\n"
        f"<b>🔑</b> License until: {row[4]}\n"
        f"<b>✅ Active:</b> {row[5]}    <b>⛔ Blocked:</b> {row[6]}",
        parse_mode=ParseMode.HTML
    )

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML)
        return
    kws = [k.strip().lower() for k in " ".join(context.args).split(",") if k.strip()]
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    inserted = add_keywords(u.id, kws)
    current = list_keywords(u.id)
    msg = f"✅ Added {inserted} new keyword(s)." if inserted > 0 else "ℹ️ No new keywords added."
    await update.message.reply_text(
        msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
        parse_mode=ParseMode.HTML
    )

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Delete keywords. Example:\n<code>/delkeyword logo, sales</code>",
            parse_mode=ParseMode.HTML)
        return
    kws = [k.strip().lower() for k in " ".join(context.args).split(",") if k.strip()]
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    removed = delete_keywords(u.id, kws)
    left = list_keywords(u.id)
    await update.message.reply_text(
        f"🗑 Removed {removed} keyword(s).\n\nCurrent keywords:\n• " +
        (", ".join(left) if left else "—"),
        parse_mode=ParseMode.HTML
    )

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
         InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]
    ])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# --------- Selftest (patched) ---------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        job_text = (
            "<b>Email Signature from Existing Logo</b>\n"
            "<b>Budget:</b> 10–30 USD\n"
            "<b>Source:</b> Freelancer\n"
            "<b>Match:</b> logo\n"
            "✏️ Create an editable email signature based on provided logo.\n"
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
            "<b>Budget:</b> 50–120 GBP (~$60–145 USD)\n"
            "<b>Source:</b> PeoplePerHour\n"
            "<b>Match:</b> logo\n"
            "🎨 Design a modern, minimal logo for UK startup.\n"
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
        record_event('freelancer')
        record_event('peopleperhour')
    except Exception as e:
        log.exception("selftest failed: %s", e)

# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin."); return
    with get_session() as s:
        rows = s.execute(text(
            "SELECT id, telegram_id, trial_until, access_until, is_active, is_blocked "
            "FROM users ORDER BY id DESC LIMIT 200"
        )).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = count_keywords(uid)
        lines.append(
            f"• <a href='tg://user?id={tid}'>{tid}</a> — kw:{kwc} | trial:{trial_end} | lic:{lic} | "
            f"A:{'✅' if act else '❌'} B:{'✅' if blk else '❌'}"
        )
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}")
        return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours.")
        return
    txt = "📊 Feed status (last %dh):\n" % STATS_WINDOW_HOURS
    txt += "\n".join([f"• {k}: {v}" for k, v in stats.items()])
    await update.effective_chat.send_message(txt)

async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <id> <days>"); return
    tid = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text('UPDATE users SET access_until=:dt WHERE telegram_id=:tid'),
                  {"dt": until, "tid": tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tid}.")
    try:
        await context.bot.send_message(chat_id=tid,
            text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception: pass

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.message.reply_text("Usage: /block <id>"); return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text('UPDATE users SET is_blocked=TRUE WHERE telegram_id=:tid'), {"tid": tid}); s.commit()
    await update.message.reply_text(f"⛔ Blocked {tid}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.message.reply_text("Usage: /unblock <id>"); return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text('UPDATE users SET is_blocked=FALSE WHERE telegram_id=:tid'), {"tid": tid}); s.commit()
    await update.message.reply_text(f"✅ Unblocked {tid}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <text>"); return
    txt = " ".join(context.args)
    with get_session() as s:
        ids = [r[0] for r in s.execute(text(
            'SELECT telegram_id FROM users WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()]
    for tid in ids:
        try:
            await context.bot.send_message(chat_id=tid, text=txt, parse_mode=ParseMode.HTML)
        except Exception: pass
    await update.message.reply_text(f"📣 Broadcast sent to {len(ids)} users.")

# ---------- Callbacks ----------
def _extract_card_title(text_html: str) -> str:
    m = re.search(r"<b>([^<]+)</b>", text_html or "", flags=re.IGNORECASE)
    if m: return m.group(1).strip()
    return (text_html.splitlines()[0] if text_html else "")[:200] or "Saved job"

async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = (q.data or "").strip()
    if data == "act:addkw":
        await q.message.reply_text(
            "Add keywords with:\n<code>/addkeyword logo, lighting</code>\n"
            "Remove: <code>/delkeyword logo</code> • Clear: <code>/clearkeywords</code>",
            parse_mode=ParseMode.HTML); await q.answer(); return

    if data == "act:settings":
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            kws = list_keywords(u.id)
            row = s.execute(text(
                "SELECT countries, proposal_template, started_at, trial_until, access_until, is_active, is_blocked "
                "FROM users WHERE id=:id"
            ), {"id": u.id}).fetchone()
        txt = (
            f"<b>🛠 Your Settings</b>\n"
            f"• <b>Keywords:</b> {', '.join(kws) if kws else '(none)'}\n"
            f"• <b>Countries:</b> {row[0] or 'ALL'}\n"
            f"• <b>Proposal template:</b> {'(saved)' if row[1] else '(none)'}\n\n"
            f"<b>●</b> Start date: {row[2]}\n"
            f"<b>●</b> Trial ends: {row[3]}\n"
            f"<b>🔑</b> License until: {row[4]}\n"
            f"<b>✅ Active:</b> {row[5]}    <b>⛔ Blocked:</b> {row[6]}"
        )
        await q.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer(); return

    if data == "act:help":
        await q.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return

    if data == "act:contact":
        await q.message.reply_text("Send a message for the admin. After they tap Reply, this becomes a chat.")
        await q.answer(); return

    if data == "act:admin":
        if not is_admin_user(q.from_user.id):
            await q.answer("Not allowed", show_alert=True); return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "<code>/users</code> • <code>/grant &lt;id&gt; &lt;days&gt;</code>\n"
            "<code>/block &lt;id&gt;</code> • <code>/unblock &lt;id&gt;</code>\n"
            "<code>/broadcast &lt;text&gt;</code> • <code>/feedstatus</code>",
            parse_mode=ParseMode.HTML)
        await q.answer(); return
    await q.answer()

# ---------- Router ----------
async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    text_msg = update.message.text.strip()
    sender_id = update.effective_user.id
    app = context.application

    if is_admin_user(sender_id):
        paired_user = app.bot_data.setdefault("pairs", {}).get(sender_id)
        if paired_user:
            try: await context.bot.send_message(chat_id=paired_user, text=text_msg)
            except Exception: pass
            return

    for aid in all_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=f"✉️ <b>New message from</b> <code>{sender_id}</code>:\n\n{text_msg}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{sender_id}")]
                ])
            )
        except Exception: pass
    await update.message.reply_text("Thanks! Your message was forwarded to the admin 👌")

# ---------- Expiry reminders ----------
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc); soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text(
            "SELECT telegram_id, COALESCE(access_until, trial_until) "
            "FROM users WHERE is_active=TRUE AND is_blocked=FALSE"
        )).fetchall()
    for tid, expiry in rows:
        if not expiry: continue
        if getattr(expiry, "tzinfo", None) is None: expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            try:
                hours_left = int((expiry - now).total_seconds() // 3600)
                await context.bot.send_message(
                    chat_id=tid,
                    text=f"⏰ Reminder: your access expires in about {hours_left} hours "
                         f"(on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).")
            except Exception: pass

async def _background_expiry_loop(app: Application):
    await asyncio.sleep(5)
    while True:
        try:
            ctx = SimpleNamespace(bot=app.bot)
            await notify_expiring_job(ctx)  # type: ignore
        except Exception as e:
            log.exception("expiry loop error: %s", e)
        await asyncio.sleep(3600)

# ---------- Build app ----------
def build_application() -> Application:
    ensure_schema(); ensure_feed_events_schema(); ensure_keyword_unique()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
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
    app.add_handler(CommandHandler("feetstatus", feetstatus_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # Expiry scheduler
    try:
        if JobQueue is not None:
            jq = app.job_queue or JobQueue()
            if app.job_queue is None: jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)
            log.info("Scheduler: JobQueue active")
        else:
            raise RuntimeError("no jobqueue")
    except Exception:
        app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
        log.info("Scheduler: fallback loop started immediately")
    return app
