# bot.py — stable version
import os, logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from db_events import ensure_feed_events_schema

from handlers_start import start_command
try:
    from handlers_ui import handle_ui_callback, handle_user_message
except Exception:
    async def handle_ui_callback(*args, **kwargs): return None
    async def handle_user_message(*args, **kwargs): return None

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN")

def build_application():
    ensure_feed_events_schema()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_ui_callback, pattern=r"^(ui|act):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    return app

application = build_application()
