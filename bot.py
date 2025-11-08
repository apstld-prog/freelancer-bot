
# bot.py â€” 5-file fix (uses TELEGRAM_BOT_TOKEN or BOT_TOKEN)
import os, logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from db import ensure_schema
from db_events import ensure_feed_events_schema

# Handlers (no setup() import needed)
from handlers_start import start_command
try:
    from handlers_ui import handle_ui_callback, handle_user_message
except Exception:
    # Fallback dummies if UI handlers are missing
    async def handle_ui_callback(*args, **kwargs): return None
    async def handle_user_message(*args, **kwargs): return None

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN (preferred) or BOT_TOKEN in environment/config")

def build_application():
    ensure_schema()
    ensure_feed_events_schema()
    app = ApplicationBuilder().token(TOKEN).build()
    # wire handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_ui_callback, pattern=r"^(ui|act):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    return app

# Expose application for server.py
application = build_application()



