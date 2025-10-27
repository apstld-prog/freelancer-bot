import asyncio
import re
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    JobQueue,
)
from sqlalchemy import text

from db import get_session, ensure_schema
from utils import (
    get_or_create_user_by_tid, add_keywords, list_keywords, delete_keywords,
    count_keywords, ensure_feed_events_schema, record_event,
    is_admin_user, all_admin_ids, help_footer, HELP_EN, STATS_WINDOW_HOURS
)

BOT_TOKEN = "<SECRET>"
TRIAL_DAYS = 10

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

def welcome_text(expiry):
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M UTC") if expiry else "N/A"
    return (
        f"👋 Welcome to <b>Freelancer Alert Bot</b>!\n\n"
        f"Your free trial expires on <b>{expiry_str}</b>.\n\n"
        "Use /addkeyword to set keywords (e.g. /addkeyword logo, lighting)\n"
        "Then you’ll start receiving job alerts instantly."
    )

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
            # ✅ FIXED: proper SQL INTERVAL usage
            s.execute(text(f"""
                UPDATE users
                SET trial_until = COALESCE(trial_until, (NOW() AT TIME ZONE 'UTC') + INTERVAL '{TRIAL_DAYS} days')
                WHERE id = :id
            """), {"id": u.id})
            expiry = s.execute(text(
                "SELECT COALESCE(access_until, trial_until) FROM users WHERE id=:id"
            ), {"id": u.id}).scalar()
            s.commit()
            log.info(f"/start executed for {update.effective_user.id} — expiry={expiry}")
    except Exception as e:
        log.exception("⚠️ start_cmd DB fallback: %s", e)

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
# ---------- Commands ----------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML)
        return
    kws = [k.strip().lower() for k in " ".join(context.args).split(",") if k.strip()]
    if not kws:
        await update.message.reply_text("No valid keywords provided.")
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    added = add_keywords(u.id, kws)
    all_kws = list_keywords(u.id)
    msg = f"✅ Added {added} new keyword(s)." if added else "No new keywords added."
    await update.message.reply_text(
        msg + "\n\nCurrent keywords:\n• " + (", ".join(all_kws) if all_kws else "—"),
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
    all_kws = list_keywords(u.id)
    await update.message.reply_text(
        f"🗑 Removed {removed} keyword(s).\n\nCurrent keywords:\n• " + (", ".join(all_kws) if all_kws else "—"),
        parse_mode=ParseMode.HTML
    )

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
         InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]
    ])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(text(
            "SELECT countries, proposal_template, started_at, trial_until, access_until, is_active, is_blocked "
            "FROM users WHERE id=:id"
        ), {"id": u.id}).fetchone()
    text_info = (
        f"<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {', '.join(kws) if kws else '(none)'}\n"
        f"• <b>Countries:</b> {row[0] or 'ALL'}\n"
        f"• <b>Proposal template:</b> {'(saved)' if row[1] else '(none)'}\n\n"
        f"<b>●</b> Start date: {row[2]}\n"
        f"<b>●</b> Trial ends: {row[3]}\n"
        f"<b>🔑</b> License until: {row[4]}\n"
        f"<b>✅ Active:</b> {row[5]}    <b>⛔ Blocked:</b> {row[6]}"
    )
    await update.message.reply_text(text_info, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# --------- Selftest ---------
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
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
        ])
        await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.3)
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
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
        ])
        await update.effective_chat.send_message(pph_text, parse_mode=ParseMode.HTML, reply_markup=pph_kb)
        record_event("freelancer")
        record_event("peopleperhour")
    except Exception as e:
        log.exception("selftest error: %s", e)

# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    with get_session() as s:
        rows = s.execute(text(
            "SELECT id, telegram_id, trial_until, access_until, is_active, is_blocked "
            "FROM users ORDER BY id DESC LIMIT 200"
        )).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial, lic, act, blk in rows:
        kwc = count_keywords(uid)
        lines.append(
            f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial} | lic:{lic} | "
            f"A:{'✅' if act else '❌'} B:{'✅' if blk else '❌'}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /grant <id> <days>")
        return
    tid = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text("UPDATE users SET access_until=:dt WHERE telegram_id=:tid"),
                  {"dt": until, "tid": tid}); s.commit()
    await update.message.reply_text(f"✅ Granted until {until.isoformat()} for {tid}.")
    try:
        await context.bot.send_message(chat_id=tid,
            text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception:
        pass

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /block <id>")
        return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text("UPDATE users SET is_blocked=TRUE WHERE telegram_id=:tid"),
                  {"tid": tid}); s.commit()
    await update.message.reply_text(f"⛔ Blocked {tid}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unblock <id>")
        return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text("UPDATE users SET is_blocked=FALSE WHERE telegram_id=:tid"),
                  {"tid": tid}); s.commit()
    await update.message.reply_text(f"✅ Unblocked {tid}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <text>")
        return
    text_msg = " ".join(context.args)
    with get_session() as s:
        ids = [r[0] for r in s.execute(text(
            "SELECT telegram_id FROM users WHERE is_active=TRUE AND is_blocked=FALSE"
        )).fetchall()]
    sent = 0
    for tid in ids:
        try:
            await context.bot.send_message(chat_id=tid, text=text_msg, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"📣 Broadcast sent to {sent} users.")
# ---------- Callbacks ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:addkw":
        await q.message.reply_text(
            "Add keywords:\n<code>/addkeyword logo, lighting</code>\n"
            "Remove: <code>/delkeyword logo</code> • Clear: <code>/clearkeywords</code>",
            parse_mode=ParseMode.HTML)
        await q.answer()
        return

    if data == "act:settings":
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            kws = list_keywords(u.id)
            row = s.execute(text(
                "SELECT countries, proposal_template, started_at, trial_until, access_until, is_active, is_blocked "
                "FROM users WHERE id=:id"
            ), {"id": u.id}).fetchone()
        msg = (
            f"<b>🛠 Settings</b>\n"
            f"• Keywords: {', '.join(kws) if kws else '(none)'}\n"
            f"• Countries: {row[0] or 'ALL'}\n"
            f"• Proposal: {'(saved)' if row[1] else '(none)'}\n"
            f"Trial ends: {row[3]} | License: {row[4]}"
        )
        await q.message.reply_text(msg, parse_mode=ParseMode.HTML)
        await q.answer()
        return

    if data == "act:help":
        await q.message.reply_text(
            HELP_EN + help_footer(STATS_WINDOW_HOURS),
            parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer()
        return

    if data == "act:contact":
        await q.message.reply_text("Send a message to the admin. They can reply directly here.")
        await q.answer()
        return

    if data == "act:admin":
        if not is_admin_user(q.from_user.id):
            await q.answer("Not allowed", show_alert=True)
            return
        await q.message.reply_text(
            "<b>Admin Panel</b>\n"
            "/users • /grant <id> <days>\n"
            "/block <id> • /unblock <id>\n"
            "/broadcast <text> • /feedstatus",
            parse_mode=ParseMode.HTML
        )
        await q.answer()
        return

    await q.answer()

# ---------- Saved Job Delete ----------
async def saved_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not (q.data or "").startswith("saved:del:"):
        return await q.answer()
    try:
        rid = int(q.data.split(":")[2])
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            s.execute(text("DELETE FROM saved_job WHERE id=:rid AND user_id=:uid"),
                      {"rid": rid, "uid": u.id})
            s.commit()
        await q.answer("Deleted")
        if q.message:
            await q.message.delete()
    except Exception as e:
        log.exception("saved_action_cb error: %s", e)
        await q.answer("Error", show_alert=True)

# ---------- Job Save/Delete ----------
async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "")
    msg = q.message

    if data == "job:save":
        try:
            text_html = msg.text_html or msg.text or ""
            title = (re.search(r"<b>([^<]+)</b>", text_html) or ["Saved job"])[0]
            with get_session() as s:
                u = get_or_create_user_by_tid(s, q.from_user.id)
                s.execute(text(
                    "INSERT INTO saved_job (user_id,title,description) VALUES (:u,:t,:d)"
                ), {"u": u.id, "t": title, "d": text_html})
                s.commit()
            await q.answer("Saved")
        except Exception as e:
            log.exception("job_action_cb save error: %s", e)
            await q.answer("Error")
        return

    if data == "job:delete":
        try:
            if q.message:
                await q.message.delete()
            await q.answer("Deleted")
        except Exception:
            await q.answer("Failed")

# ---------- Continuous Chat Router ----------
async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    msg = update.message.text.strip()
    uid = update.effective_user.id
    app = context.application
    admins = all_admin_ids()

    if is_admin_user(uid):
        paired = context.application.bot_data.get("paired_user")
        if paired:
            await context.bot.send_message(chat_id=paired, text=msg)
            return

    for aid in admins:
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=f"✉️ Message from <code>{uid}</code>:\n\n{msg}",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    await update.message.reply_text("Thanks! Your message was forwarded to the admin 👌")

# ---------- Expiry Reminder ----------
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text(
            "SELECT telegram_id, COALESCE(access_until, trial_until) "
            "FROM users WHERE is_active=TRUE AND is_blocked=FALSE"
        )).fetchall()
    for tid, expiry in rows:
        if not expiry: continue
        if getattr(expiry, "tzinfo", None) is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            hours_left = int((expiry - now).total_seconds() // 3600)
            try:
                await context.bot.send_message(
                    chat_id=tid,
                    text=f"⏰ Reminder: your access expires in about {hours_left} hours "
                         f"(on {expiry.strftime('%Y-%m-%d %H:%M UTC')})."
                )
            except Exception:
                pass

# ---------- Build Application ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(saved_action_cb, pattern=r"^saved:del:"))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)$"))

    # Continuous chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # Scheduler / expiry reminder
    try:
        jq = app.job_queue or JobQueue()
        if app.job_queue is None:
            jq.set_application(app)
        jq.run_repeating(notify_expiring_job, interval=3600, first=60)
        log.info("Scheduler: JobQueue enabled")
    except Exception:
        app.bot_data["expiry_task"] = asyncio.create_task(notify_expiring_job(SimpleNamespace(bot=app.bot)))
        log.info("Scheduler: fallback loop started immediately")

    return app
