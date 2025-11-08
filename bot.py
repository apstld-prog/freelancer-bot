import os, logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from db_events import ensure_feed_events_schema
from handlers_start import start_command

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN")

def build_application():
    ensure_feed_events_schema()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    return app

application = build_application()
