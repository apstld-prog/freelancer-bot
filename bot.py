# bot.py — Freelancer Alert Bot (stable full version)
import os, logging, asyncio, re
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from sqlalchemy import text

from db import ensure_schema, get_session
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords, ensure_keywords
)
from utils import (
    get_or_create_user_by_tid, is_admin_user,
    welcome_text, help_footer
)

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- UI ----------
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
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
    "<b>Keywords</b>\n"
    "• Add: <code>/addkeyword logo, lighting</code>\n"
    "• Remove: <code>/delkeyword logo</code>\n"
    "• Clear: <code>/clearkeywords</code>\n\n"
    "<b>Other</b>\n"
    "• Save proposal: <code>/setproposal &lt;text&gt;</code>\n"
    "• Test card: <code>/selftest</code>\n"
)

# ---------- Commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main /start command."""
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(text(
            "UPDATE users SET started_at = COALESCE(started_at, NOW() AT TIME ZONE 'UTC') WHERE telegram_id = :tid"
        ), {"tid": update.effective_user.id})
        s.execute(text(
            "UPDATE users SET trial_until = COALESCE(trial_until, NOW() + INTERVAL '10 days') WHERE telegram_id = :tid"
        ), {"tid": update.effective_user.id})
        expiry = s.execute(text(
            "SELECT COALESCE(access_until, trial_until) FROM users WHERE telegram_id = :tid"
        ), {"tid": update.effective_user.id}).scalar()
        s.commit()

    await update.effective_chat.send_message(
        welcome_text(expiry if isinstance(expiry, datetime) else None),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(
        HELP_EN + help_footer(24),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(24),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/addkeyword logo, lighting</code>", parse_mode=ParseMode.HTML
        )
        return
    kws = [k.strip().lower() for k in " ".join(context.args).split(",") if k.strip()]
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    inserted = add_keywords(u.id, kws)
    current = list_keywords(u.id)
    msg = (
        f"✅ Added {inserted} new keyword(s)." if inserted > 0
        else "ℹ️ Those keywords already exist (no changes)."
    )
    await update.message.reply_text(
        msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
        parse_mode=ParseMode.HTML
    )


async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/delkeyword logo, sales</code>", parse_mode=ParseMode.HTML
        )
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
async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /grant <id> <days>")
        return
    tid, days = int(context.args[0]), int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text(
            "UPDATE users SET access_until=:dt WHERE telegram_id=:tid"
        ), {"dt": until, "tid": tid})
        s.commit()
    await update.message.reply_text(f"✅ Granted until {until.strftime('%Y-%m-%d')} for {tid}")
    try:
        await context.bot.send_message(
            chat_id=tid,
            text=f"🔑 Your access was extended until {until.strftime('%Y-%m-%d %H:%M UTC')}."
        )
    except Exception:
        pass


async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /block <id>")
        return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text("UPDATE users SET is_blocked=TRUE WHERE telegram_id=:tid"), {"tid": tid})
        s.commit()
    await update.message.reply_text(f"⛔ Blocked {tid}.")


async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unblock <id>")
        return
    tid = int(context.args[0])
    with get_session() as s:
        s.execute(text("UPDATE users SET is_blocked=FALSE WHERE telegram_id=:tid"), {"tid": tid})
        s.commit()
    await update.message.reply_text(f"✅ Unblocked {tid}.")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <text>")
        return
    txt = " ".join(context.args)
    with get_session() as s:
        ids = [
            r[0]
            for r in s.execute(
                text("SELECT telegram_id FROM users WHERE is_active=TRUE AND is_blocked=FALSE")
            ).fetchall()
        ]
    for tid in ids:
        try:
            await context.bot.send_message(chat_id=tid, text=txt, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    await update.message.reply_text(f"📣 Broadcast sent to {len(ids)} users.")


# ---------- Keyword clear callback ----------
async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    agree = (q.data or "").endswith("yes")
    if not agree:
        await q.message.reply_text("Cancelled.")
        await q.answer()
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
    n = clear_keywords(u.id)
    await q.message.reply_text(f"🗑 Cleared {n} keyword(s).")
    await q.answer()


# ---------- Selftest command ----------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends two fake job cards to verify bot messages."""
    try:
        job_text = (
            "<b>Test Job — Freelancer</b>\n"
            "<b>Budget:</b> $50–100 USD\n"
            "<b>Source:</b> Freelancer.com\n"
            "<b>Match:</b> logo\n"
            "Create a simple responsive logo banner."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal", url="https://www.freelancer.com"),
             InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com")],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
        ])
        await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.5)

        pph_text = (
            "<b>Logo Design Project</b>\n"
            "<b>Budget:</b> £60 (~$75 USD)\n"
            "<b>Source:</b> PeoplePerHour\n"
            "<b>Match:</b> logo\n"
            "Minimal clean logo design required."
        )
        await update.effective_chat.send_message(
            pph_text, parse_mode=ParseMode.HTML, reply_markup=kb
        )
    except Exception as e:
        log.exception("selftest failed: %s", e)


# ---------- Save job / delete ----------
async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "")
    msg = q.message
    if data == "job:delete":
        try:
            if msg:
                await msg.delete()
        except Exception:
            pass
        await q.answer("Deleted")
        return

    if data == "job:save":
        try:# ---------- Background expiry notifier ----------
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    """Notify users with expiring access (trial or premium)."""
    try:
        with get_session() as s:
            rows = s.execute(text("""
                SELECT telegram_id, COALESCE(access_until, trial_until)
                FROM users
                WHERE is_blocked=FALSE
                  AND COALESCE(access_until, trial_until) < NOW() + INTERVAL '2 days'
                  AND COALESCE(access_until, trial_until) > NOW()
            """)).fetchall()
        for tid, until in rows:
            try:
                left = (until - datetime.now(timezone.utc)).days
                await context.bot.send_message(
                    chat_id=tid,
                    text=f"⏳ Your access expires in {left} day(s). Renew soon!"
                )
            except Exception:
                pass
    except Exception as e:
        log.error("expiry loop error: %s", e)


async def _background_expiry_loop(app: Application):
    while True:
        try:
            await notify_expiring_job(SimpleNamespace(bot=app.bot))
        except Exception as e:
            log.error("expiry loop error: %s", e)
        await asyncio.sleep(86400)


# ---------- Build Application ----------
def build_application() -> Application:
    ensure_schema()
    ensure_keyword_unique()
    ensure_keywords()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear"))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:"))

    asyncio.create_task(_background_expiry_loop(app))
    return app


# ---------- Entry Point ----------
if __name__ == "__main__":
    import uvicorn
    from server import app as fastapi_app
    from threading import Thread

    def _run_fastapi():
        uvicorn.run(fastapi_app, host="0.0.0.0", port=10000, log_level="info")

    Thread(target=_run_fastapi, daemon=True).start()
    loop = asyncio.get_event_loop()
    app = build_application()
    loop.run_until_complete(app.initialize())
    log.info("✅ Application initialized successfully.")
    loop.run_until_complete(app.start())
    loop.run_forever()

            from sqlalchemy import text as _t
            from db import get_session as _gs, get_or_create_user_by_tid as _get_user
            with _gs() as s:
                u = _get_user(s, q.from_user.id)
                s.execute(_t("""
                    CREATE TABLE IF NOT EXISTS saved_job (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        title TEXT,
                        description TEXT,
                        url TEXT,
                        saved_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')
                    )
                """))
                s.execute(_t("""
                    INSERT INTO saved_job (user_id, title, description, url)
                    VALUES (:uid, :t, :d, :u)
                """), {"uid": u.id, "t": msg.text or "(no title)",
                       "d": msg.text or "", "u": ""})
                s.commit()
        except Exception as e:
            log.warning("job:save error: %s", e)
        await q.answer("Saved")


async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML
    )


# ---------- Admin commands ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin.")
        return
    with get_session() as s:
        rows = s.execute(text(
            "SELECT id, telegram_id, trial_until, access_until, is_active, is_blocked "
            "FROM users ORDER BY id DESC LIMIT 50"
        )).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial, access, act, blk in rows:
        lines.append(
            f"• <a href='tg://user?id={tid}'>{tid}</a> "
            f"| trial:{trial} | access:{access} | "
            f"A:{'✅' if act else '❌'} B:{'✅' if blk else '❌'}"
        )
    await update.effective_chat.send_message(
        "\n".join(lines), parse_mode=ParseMode.HTML
    )
