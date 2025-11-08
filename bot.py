
# bot.py — minimal, stable, webhook-friendly (5-file fix)
import os, logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from config import BOT_TOKEN
from db import ensure_schema
from db_events import ensure_feed_events_schema

# use existing handlers (no setup() imports)
from handlers_start import start_command
from handlers_ui import handle_ui_callback, handle_user_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN in config.py / env")

def build_application():
    ensure_schema()
    ensure_feed_events_schema()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", start_command))
    # callbacks & generic text
    app.add_handler(CallbackQueryHandler(handle_ui_callback, pattern=r"^(ui|act):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    return app

# Compatibility: some imports expect 'application'
application = build_application()

async def on_startup():
    log.info("✅ Telegram bot startup")

async def on_shutdown():
    log.info("🛑 Telegram bot shutdown")
