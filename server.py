import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse

from telegram.ext import ApplicationBuilder
from telegram import Update

from config import TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET

from handlers_start import register_start_handlers
from handlers_settings import register_settings_handlers
from handlers_jobs import register_jobs_handlers
from handlers_help import register_help_handlers
from handlers_admin import register_admin_handlers
from handlers_ui import register_ui_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI()

# Read environment
PORT = int(os.getenv("PORT", 10000))
RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not RENDER_HOSTNAME:
    raise RuntimeError("❌ Environment variable RENDER_EXTERNAL_HOSTNAME is missing!")

WEBHOOK_URL = f"https://{RENDER_HOSTNAME}/{WEBHOOK_SECRET}"

# Build telegram application
application = (
    ApplicationBuilder()
    .token(TELEGRAM_BOT_TOKEN)
    .concurrent_updates(True)
    .build()
)

# Register handlers
register_start_handlers(application)
register_settings_handlers(application)
register_jobs_handlers(application)
register_help_handlers(application)
register_admin_handlers(application)
register_ui_handlers(application)


# --------------------------------------------------------
# 🚀 Startup: set webhook + start bot dispatcher
# --------------------------------------------------------
@app.on_event("startup")
async def startup():
    logger.info("🚀 FastAPI startup…")

    # Delete old webhook
    await application.bot.delete_webhook(drop_pending_updates=True)

    # Set new webhook
    result = await application.bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=["message", "callback_query"],
    )

    logger.info("====================================")
    logger.info(f"🌍 Webhook set → {WEBHOOK_URL}")
    logger.info(f"Webhook result: {result}")
    logger.info("====================================")

    # Start bot
    await application.initialize()
    await application.start()


@app.on_event("shutdown")
async def shutdown():
    logger.info("🔻 Shutting down bot")
    await application.stop()
    await application.shutdown()


# --------------------------------------------------------
# Health check
# --------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h3>✅ Freelancer Alert Bot is running properly.</h3>"


# --------------------------------------------------------
# Webhook endpoint — FULL FIX FOR PTB v20+
# --------------------------------------------------------
@app.post(f"/{WEBHOOK_SECRET}")
async def telegram_hook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)

        return JSONResponse({"ok": True})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
