# ==============================================================
# app.py â€” FINAL WEBHOOK VERSION (Nov 2025)
# ==============================================================

import os
import logging
from fastapi import FastAPI, Request
from telegram import Update

from bot import build_application, on_startup as bot_startup, on_shutdown as bot_shutdown

log = logging.getLogger("app")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render gives this automatically

if not BOT_TOKEN:
    raise RuntimeError("âŒ Missing TELEGRAM_BOT_TOKEN")

if not WEBHOOK_URL:
    raise RuntimeError("âŒ Missing RENDER_EXTERNAL_URL")


# --------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------
app = FastAPI()

telegram_app = build_application()


# --------------------------------------------------------------
# Startup â€” proper PTB initialization
# --------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    log.info("ðŸš€ Starting Telegram botâ€¦")

    await telegram_app.initialize()
    await telegram_app.start()
    await bot_startup()

    webhook_url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"

    await telegram_app.bot.delete_webhook()
    await telegram_app.bot.set_webhook(url=webhook_url)

    log.info(f"âœ… Webhook set: {webhook_url}")


# --------------------------------------------------------------
# Shutdown â€” proper PTB cleanup
# --------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    log.info("ðŸ›‘ Stopping Telegram botâ€¦")

    await telegram_app.stop()
    await telegram_app.shutdown()
    await bot_shutdown()

    log.info("âœ… Bot stopped.")


# --------------------------------------------------------------
# Webhook Receiver
# --------------------------------------------------------------
@app.post("/webhook/{token}")
async def telegram_webhook(request: Request, token: str):
    if token != BOT_TOKEN:
        return {"status": "forbidden"}

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)

    await telegram_app.process_update(update)
    return {"status": "ok"}


# --------------------------------------------------------------
# Health check
# --------------------------------------------------------------
@app.get("/")
async def health():
    return {"status": "running", "mode": "webhook"}

