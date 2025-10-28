import asyncio
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
)

from fastapi import FastAPI
import uvicorn

from db import get_session, ensure_schema
from utils import (
    get_or_create_user_by_tid,
    is_admin_user,
    welcome_text,
    help_footer,
    format_currency,
    format_time_ago,
)
from db_keywords import ensure_keywords
from handlers_start import register_start_handlers
from handlers_help import register_help_handlers
from handlers_jobs import register_job_handlers
from handlers_settings import register_settings_handlers

log = logging.getLogger("bot")
app = Application.builder().token("YOUR_BOT_TOKEN_HERE").build()
fastapi_app = FastAPI()

TRIAL_DAYS = 10
STATS_WINDOW_HOURS = 24

# ========== MAIN MENU KEYBOARD ==========
def main_menu_kb(is_admin=False):
    buttons = [
        [InlineKeyboardButton("📰 Latest Jobs", callback_data="act:latest_jobs")],
        [InlineKeyboardButton("🔍 Search Jobs", callback_data="act:search_jobs")],
        [InlineKeyboardButton("⭐ Saved List", callback_data="act:saved_jobs")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
    ]
    if is_admin:
        buttons.append(
            [InlineKeyboardButton("🛠 Admin Panel", callback_data="act:admin_panel")]
        )
    return InlineKeyboardMarkup(buttons)


# ========== START COMMAND ==========
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = (update.effective_user.id if update and update.effective_user else None)
    cid = (update.effective_chat.id if update and update.effective_chat else None)
    log.info("start_cmd: entered for uid=%s chat=%s", uid, cid)
    try:
        from sqlalchemy import text as _text
        with get_session() as s:
            u = get_or_create_user_by_tid(s, uid)
            log.info("start_cmd: ensured users.id=%s for tid=%s", getattr(u, "id", None), uid)

            s.execute(_text(
                "UPDATE users SET started_at=COALESCE(started_at, NOW() AT TIME ZONE 'UTC') WHERE id=:id"
            ), {"id": u.id})

            s.execute(
                _text("UPDATE users SET trial_until=COALESCE(trial_until, (NOW() AT TIME ZONE 'UTC') + INTERVAL ':days days') WHERE id=:id")
                .bindparams(days=TRIAL_DAYS),
                {"id": u.id},
            )

            expiry = s.execute(_text(
                "SELECT COALESCE(access_until, trial_until) FROM users WHERE id=:id"
            ), {"id": u.id}).scalar()
            s.commit()

        text_welcome = welcome_text(expiry if isinstance(expiry, datetime) else None)
        kb = main_menu_kb(is_admin=is_admin_user(uid))

        if cid is not None:
            await context.bot.send_message(chat_id=cid, text=text_welcome, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await update.effective_chat.send_message(text_welcome, parse_mode=ParseMode.HTML, reply_markup=kb)
        log.info("start_cmd: welcome sent to uid=%s", uid)

        help_msg = "Here are the available options:\n\n" + help_footer(STATS_WINDOW_HOURS)
        if cid is not None:
            await context.bot.send_message(chat_id=cid, text=help_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        else:
            await update.effective_chat.send_message(help_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        log.info("start_cmd: help sent to uid=%s", uid)

    except Exception as e:
        log.exception("start_cmd: FAILED for uid=%s: %s", uid, e)
        try:
            safe_txt = "Sorry — something went wrong while starting your session. Please try again."
            if cid is not None:
                await context.bot.send_message(chat_id=cid, text=safe_txt)
            elif update and update.effective_chat:
                await update.effective_chat.send_message(safe_txt)
        except Exception:
            pass
# ========== EXPIRY LOOP ==========
async def notify_expiring_job(ctx):
    from sqlalchemy import text as _text
    with get_session() as s:
        rows = s.execute(_text(
            "SELECT telegram_id, COALESCE(access_until, trial_until) "
            "FROM users WHERE is_active=TRUE AND is_blocked=FALSE"
        )).fetchall()
        for r in rows:
            tid, exp = r
            if exp and isinstance(exp, datetime):
                remaining = (exp - datetime.utcnow()).total_seconds() / 3600
                if 0 < remaining <= 24:
                    try:
                        await ctx.bot.send_message(
                            chat_id=tid,
                            text=f"⚠️ Your access expires in {int(remaining)} hours. Renew now to keep receiving alerts."
                        )
                    except Exception as e:
                        log.warning("Notify failed for %s: %s", tid, e)

# ========== BACKGROUND EXPIRY LOOP ==========
async def _background_expiry_loop(ctx):
    log.info("⏳ Background expiry loop started")
    while True:
        try:
            await notify_expiring_job(ctx)
            await asyncio.sleep(3600)
        except Exception as e:
            log.error("expiry loop error: %s", e)
            await asyncio.sleep(3600)

# ========== BUILD APPLICATION ==========
def build_application():
    ensure_schema()
    ensure_keywords()
    log.info("✅ Database schema and keywords ensured")

    app.add_handler(CommandHandler("start", start_cmd))
    register_start_handlers(app)
    register_help_handlers(app)
    register_job_handlers(app)
    register_settings_handlers(app)

    jq = app.job_queue or JobQueue()
    jq.set_application(app)
    jq.run_repeating(lambda ctx: asyncio.create_task(_background_expiry_loop(ctx)), interval=3600, first=10)

    log.info("✅ Handlers and background tasks registered")
    return app

# ========== FASTAPI WEBHOOK ENDPOINT ==========
@fastapi_app.post("/webhook/hook-secret-777")
async def telegram_webhook(update: dict):
    update_obj = Update.de_json(update, app.bot)
    await app.process_update(update_obj)
    return {"ok": True}
# ========== MAIN ENTRY ==========
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    log.info("🚀 Starting Freelancer Alert Bot")
    ensure_schema()
    ensure_keywords()
    built_app = build_application()

    loop = asyncio.get_event_loop()
    loop.create_task(_background_expiry_loop(built_app))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=10000)
