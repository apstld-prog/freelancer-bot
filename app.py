# ==============================================================
# app.py — FINAL WEBHOOK VERSION (Nov 2025)
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
    raise RuntimeError("❌ Missing TELEGRAM_BOT_TOKEN")

if not WEBHOOK_URL:
    raise RuntimeError("❌ Missing RENDER_EXTERNAL_URL")


# --------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------
app = FastAPI()

telegram_app = build_application()


# --------------------------------------------------------------
# Startup — proper PTB initialization
# --------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    log.info("🚀 Starting Telegram bot…")

    await telegram_app.initialize()
    await telegram_app.start()
    await bot_startup()

    webhook_url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"

    await telegram_app.bot.delete_webhook()
    await telegram_app.bot.set_webhook(url=webhook_url)

    log.info(f"✅ Webhook set: {webhook_url}")


# --------------------------------------------------------------
# Shutdown — proper PTB cleanup
# --------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    log.info("🛑 Stopping Telegram bot…")

    await telegram_app.stop()
    await telegram_app.shutdown()
    await bot_shutdown()

    log.info("✅ Bot stopped.")


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
