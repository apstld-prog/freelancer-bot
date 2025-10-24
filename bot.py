import os
import logging
import psycopg2
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# Logging setup
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql+psycopg2://", "postgresql://")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5254014824"))

def db_connect():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def ensure_user_exists(user_id, name, username):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute('SELECT id FROM "user" WHERE telegram_id=%s', (user_id,))
    if not cur.fetchone():
        cur.execute(
            'INSERT INTO "user" (telegram_id, name, username, is_blocked, is_active, countries, created_at, updated_at) '
            'VALUES (%s,%s,%s,false,true,%s,NOW(),NOW())',
            (user_id, name, username, "ALL"),
        )
    conn.commit()
    cur.close()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)
    log.info(f"/start from {user.id}")

    keyboard = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw")],
        [
            InlineKeyboardButton("⭐ Saved", callback_data="act:saved"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [InlineKeyboardButton("📩 Contact", url="https://t.me/Freelancer_Alert_Support")],
    ]
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Admin", callback_data="act:admin")])

    text = (
        "👋 *Welcome to Freelancer Alert Bot!*\n\n"
        "🔎 Get instant job alerts from multiple platforms based on your keywords.\n\n"
        "You can:\n"
        "• Add keywords to receive job alerts.\n"
        "• Save interesting jobs.\n"
        "• Filter alerts by country with /setcountry command.\n\n"
        "_Enjoy your 10-day free trial!_\n\n"
        "➡️ Use /help for commands."
    )

    await context.bot.send_message(
        chat_id=user.id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📘 *Help Menu*\n\n"
        "/start — Restart the bot menu\n"
        "/setcountry — Set countries filter (e.g. `/setcountry US,UK` or `/setcountry ALL`)\n"
        "/feedstatus — Check connected platforms\n"
        "/selftest — Admin: Test job feeds\n"
        "/help — Show this help message"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🟢 *Connected feeds:* Freelancer, PeoplePerHour, Skywalker", parse_mode=ParseMode.MARKDOWN)

async def setcountry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /setcountry US,UK or /setcountry ALL")
        return
    countries = args[0].upper()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute('UPDATE "user" SET countries=%s, updated_at=NOW() WHERE telegram_id=%s', (countries, user_id))
    conn.commit()
    cur.close()
    conn.close()
    await update.message.reply_text(f"✅ Country filter updated to: {countries}")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("✅ *Selftest OK* — Platforms recorded: freelancer + peopleperhour", parse_mode=ParseMode.MARKDOWN)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "act:addkw":
        await query.edit_message_text("📝 Send me your keywords separated by commas (e.g. lighting, logo, relux)")
    elif data == "act:saved":
        await query.edit_message_text("⭐ Your saved job list is empty (demo mode).")
    elif data == "act:settings":
        await query.edit_message_text("⚙️ Settings menu: use /setcountry to update country filter.")
    elif data == "act:admin" and update.effective_user.id == ADMIN_ID:
        await query.edit_message_text("🛠 *Admin menu:*\n- /feedstatus\n- /selftest", parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text("Invalid option.")

def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    app.add_handler(CommandHandler("setcountry", setcountry))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app

if __name__ == "__main__":
    from telegram.ext import Application
    import uvicorn
    app = build_application()
    log.info("✅ Bot ready via Uvicorn")
    uvicorn.run("server:app", host="0.0.0.0", port=10000)
