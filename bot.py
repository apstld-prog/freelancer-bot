import os, logging, asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Bot

from db import ensure_schema
from db_events import ensure_feed_events_schema

from handlers_start import start_command
from handlers_ui import handle_ui_callback, handle_user_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN")

WEBHOOK_BASE = os.getenv("WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")
if WEBHOOK_BASE:
    WEBHOOK_URL = WEBHOOK_BASE.rstrip("/") + f"/webhook/{TOKEN}"
else:
    WEBHOOK_URL = None
    log.warning("⚠️ No WEBHOOK_BASE_URL or RENDER_EXTERNAL_URL set.")

def build_application():
    ensure_schema()
    ensure_feed_events_schema()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_ui_callback, pattern=r"^(ui|act):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    return app

application = build_application()

# ---- AUTO SET WEBHOOK ----
async def _set_webhook():
    if WEBHOOK_URL:
        bot = Bot(TOKEN)
        await bot.delete_webhook()
        await bot.set_webhook(url=WEBHOOK_URL)
        log.info(f"✅ Webhook set: {WEBHOOK_URL}")
    else:
        log.warning("❌ Webhook NOT set — missing WEBHOOK_BASE_URL or RENDER_EXTERNAL_URL")

asyncio.get_event_loop().run_until_complete(_set_webhook())
