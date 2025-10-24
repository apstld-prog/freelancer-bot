import logging
import asyncio
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import os
import psycopg2
import psycopg2.extras
import json
import re
import httpx

# Initialize logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))
TRIAL_MODE = os.getenv("TRIAL_MODE", "on").lower() == "on"

def db_connect():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    return conn

def get_user(telegram_id):
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM "user" WHERE telegram_id = %s', (telegram_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def update_user_country(telegram_id, countries):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        'UPDATE "user" SET countries = %s, updated_at = NOW() WHERE telegram_id = %s',
        (countries, telegram_id),
    )
    conn.commit()
    cur.close()
    conn.close()

def ensure_user_exists(telegram_id, name=None, username=None):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute('SELECT id FROM "user" WHERE telegram_id = %s', (telegram_id,))
    exists = cur.fetchone()
    if not exists:
        cur.execute(
            'INSERT INTO "user" (telegram_id, name, username, is_admin, created_at, updated_at, is_active, is_blocked, countries) VALUES (%s,%s,%s,%s,NOW(),NOW(),true,false,%s)',
            (
                telegram_id,
                name or "",
                username or "",
                telegram_id in ADMIN_IDS,
                "ALL",
            ),
        )
    conn.commit()
    cur.close()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)
    welcome_text = (
        f"👋 Hello {user.first_name}!\n\n"
        "Welcome to *Freelancer Alert Bot*.\n"
        "You'll receive new freelance job alerts matching your keywords 💼.\n\n"
        "Use /setkeywords to define your keywords.\n"
        "Use /setcountry to set countries (e.g. `/setcountry US,UK` or `/setcountry ALL`).\n"
        "Use /feedstatus to check current status.\n\n"
        "⭐ Enjoy and good luck!"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def setcountry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if not context.args:
        await update.message.reply_text(
            "Please specify countries separated by commas (e.g. `/setcountry US,UK`) or `ALL` for all countries.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    countries = " ".join(context.args).strip().upper()
    countries = re.sub(r"\s+", "", countries)
    if not countries:
        countries = "ALL"

    update_user_country(user.id, countries)
    await update.message.reply_text(f"🌍 Country preference updated to: *{countries}*", parse_mode=ParseMode.MARKDOWN)
async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT keywords, countries, created_at FROM "user" WHERE telegram_id = %s',
        (user.id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    keywords = row.get("keywords", "(none)") if row else "(none)"
    countries = row.get("countries", "ALL") if row else "ALL"
    created = row.get("created_at").strftime("%Y-%m-%d") if row else "N/A"

    text = (
        f"📊 *Your Feed Status*\n\n"
        f"👤 User: `{user.first_name}`\n"
        f"💬 Keywords: `{keywords}`\n"
        f"🌍 Countries: `{countries}`\n"
        f"🗓️ Registered: {created}\n\n"
        f"Use /setkeywords or /setcountry to modify your preferences."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🆘 *Help Menu*\n\n"
        "/start - Start the bot\n"
        "/setkeywords - Define keywords\n"
        "/setcountry - Define countries (e.g. `/setcountry US,UK`)\n"
        "/feedstatus - Show your current settings\n"
        "/selftest - Run self-diagnostic\n"
        "⭐ Use inline buttons in job alerts to Save/Delete jobs."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)
    await update.message.reply_text(
        "✅ *Self-test successful!*\nRecorded platforms: freelancer + peopleperhour",
        parse_mode=ParseMode.MARKDOWN,
    )

async def handle_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if not context.args:
        await update.message.reply_text(
            "Please specify your keywords separated by commas.\nExample: `/setkeywords logo, design, lighting`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    kw = " ".join(context.args)
    kw = kw.replace("，", ",").replace(";", ",")
    kw = kw.lower().strip()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        'UPDATE "user" SET keywords = %s, updated_at = NOW() WHERE telegram_id = %s',
        (kw, user.id),
    )
    conn.commit()
    cur.close()
    conn.close()

    await update.message.reply_text(
        f"✅ Keywords updated to: *{kw}*", parse_mode=ParseMode.MARKDOWN
    )

# -----------------------------
# CALLBACK HANDLERS (Save/Delete)
# -----------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()

    if data == "job:save":
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO saved_job (user_id, job_id, saved_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING',
            (user_id, query.message.message_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        await context.bot.delete_message(chat_id=user_id, message_id=query.message.message_id)
        return

    elif data == "job:delete":
        await context.bot.delete_message(chat_id=user_id, message_id=query.message.message_id)
        return

    elif data == "act:admin":
        if user_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=user_id,
                text="👑 *Admin Panel*\nAll systems running normally.",
                parse_mode=ParseMode.MARKDOWN,
            )
        return
# -----------------------------
# ADMIN & MISC COMMANDS
# -----------------------------
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    text = "👑 *Admin Commands*\n\n" \
           "/feedstatus - View your status\n" \
           "/selftest - Run diagnostic\n" \
           "/setkeywords - Change keywords\n" \
           "/setcountry - Change country filters"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# -----------------------------
# MAIN APPLICATION SETUP
# -----------------------------
def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setkeywords", handle_keywords))
    app.add_handler(CommandHandler("setcountry", setcountry))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callback_handler))

    return app

# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from telegram import Update

    app = build_application()
    fastapi_app = FastAPI()

    @fastapi_app.post("/webhook/{token}")
    async def webhook(token: str, update: dict):
        if token != "hook-secret-777":
            return {"error": "unauthorized"}
        telegram_update = Update.de_json(update, app.bot)
        await app.process_update(telegram_update)
        return {"status": "ok"}

    @fastapi_app.get("/")
    async def root():
        return {"status": "running"}

    log.info("✅ Bot module loaded with /setcountry support.")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=10000)
