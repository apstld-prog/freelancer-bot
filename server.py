# server.py
# -*- coding: utf-8 -*-
"""
FastAPI + python-telegram-bot (v20+) webhook server
- Loads Application from bot.py (build_application)
- Sets Telegram webhook to WEBHOOK_URL/webhook/WEBHOOK_SECRET
- Validates secret header: X-Telegram-Bot-Api-Secret-Token
- Health endpoints: / and /healthz
"""

import os
import json
import logging
from typing import Optional

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import PlainTextResponse, JSONResponse
import uvicorn

from telegram import Update
from telegram.error import TelegramError

from bot import build_application  # ΔΕΝ αλλάζουμε το bot.py

log = logging.getLogger("server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# -------------------- ENV --------------------
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").rstrip("/")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set (e.g. https://your-app.onrender.com)")

WEBHOOK_SECRET = (os.getenv("WEBHOOK_SECRET") or "hook-secret-777").strip()

# Render binds to PORT
PORT = int(os.getenv("PORT", "10000"))

# -------------------- App init --------------------
app = FastAPI(title="Telegram Bot Webhook")

# Build PTB Application once (global)
application = build_application()

# Ensure webhook is set at startup
@app.on_event("startup")
async def _on_startup():
    await application.initialize()
    await application.start()

    # Set webhook with secret token (Telegram will send header X-Telegram-Bot-Api-Secret-Token)
    try:
        setok = await application.bot.set_webhook(
            url=f"{WEBHOOK_URL}/webhook/{WEBHOOK_SECRET}",
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=False,
        )
        if setok:
            log.info("Webhook set to %s/webhook/%s", WEBHOOK_URL, WEBHOOK_SECRET)
        else:
            log.warning("Failed to set webhook (Telegram returned false).")
    except TelegramError as e:
        log.exception("Error setting webhook: %s", e)

@app.on_event("shutdown")
async def _on_shutdown():
    try:
        await application.updater.stop()
    except Exception:
        pass
    await application.stop()
    await application.shutdown()

# -------------------- Health --------------------
@app.get("/", response_class=PlainTextResponse)
async def index():
    return "OK"

@app.get("/healthz", response_class=JSONResponse)
async def healthz():
    return {"ok": True, "webhook": f"{WEBHOOK_URL}/webhook/{WEBHOOK_SECRET}"}

# -------------------- Webhook route --------------------
@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    # Validate path secret
    if secret != WEBHOOK_SECRET:
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    # Validate Telegram header (optional but recommended)
    hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if hdr != WEBHOOK_SECRET:
        # Some reverse proxies may drop headers; choose strict or warn+continue
        log.warning("Secret header mismatch (got %r)", hdr)
        # return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        data = await request.body()
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        update = Update.de_json(payload, application.bot)
    except Exception as e:
        log.warning("Invalid update: %s", e)
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        await application.process_update(update)
    except Exception as e:
        log.exception("process_update failed: %s", e)

    return Response(status_code=status.HTTP_200_OK)


def main():
    log.info("Starting Uvicorn on 0.0.0.0:%s", PORT)
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False, workers=1)

if __name__ == "__main__":
    main()
