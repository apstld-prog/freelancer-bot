# ==========================================================
# ✅ app.py — FASTAPI + Telegram Webhook (FINAL VERSION)
# ==========================================================

import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from bot import (
    application,
    on_startup as bot_on_startup,
    on_shutdown as bot_on_shutdown
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI()

WEBHOOK_SECRET = "hook-secret-777"

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    f"https://{os.getenv('RENDER_EXTERNAL_URL','freelancer-bot-ns7s.onrender.com')}/webhook/{WEBHOOK_SECRET}"
)

@app.get("/")
async def root():
    return PlainTextResponse("✅ Freelancer bot running")

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        await application.process_update(update)
        return PlainTextResponse("OK")
    except Exception:
        log.exception("❌ Webhook processing error")
        return PlainTextResponse("ERROR", status_code=500)

@app.on_event("startup")
async def startup_event():
    log.info("🚀 FastAPI startup")
    await bot_on_startup()

@app.on_event("shutdown")
async def shutdown_event():
    log.info("🛑 FastAPI shutdown")
    await bot_on_shutdown()
    log.info("✅ Bot stopped cleanly")
