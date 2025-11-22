# server.py — FastAPI + Telegram webhook, PTB v20+ compatible

import os
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from telegram import Update
from bot import build_application

log = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""

tg_app = None  # global Telegram application instance


# ---------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_app

    log.info("LIFESPAN: startup — building Telegram application...")
    tg_app = build_application()

    # 1) Initialize
    log.info("Initializing Telegram application...")
    await tg_app.initialize()
    log.info("Initialized OK.")

    # 2) Set webhook
    if WEBHOOK_URL:
        wh_url = f"{WEBHOOK_URL.rstrip('/')}/telegram/{BOT_TOKEN}"
        try:
            await tg_app.bot.set_webhook(wh_url)
            log.info("Webhook set OK: %s", wh_url)
        except Exception as e:
            log.exception("Webhook error: %s", e)

    # 3) Start
    log.info("Starting Telegram application...")
    await tg_app.start()
    log.info("Telegram application started.")

    # Enter app
    try:
        yield
    finally:
        # Shutdown
        log.info("LIFESPAN: shutdown — stopping Telegram application...")
        try:
            await tg_app.stop()
        except Exception as e:
            log.exception("Stop error: %s", e)
        log.info("Telegram app stopped.")


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------
@app.get("/")
async def root():
    return PlainTextResponse("Freelancer Alert Bot web service is up.", status_code=200)


# ---------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------
@app.post("/telegram/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        return PlainTextResponse("Invalid token", status_code=403)

    global tg_app
    if tg_app is None:
        return PlainTextResponse("Bot not ready", status_code=503)

    try:
        data = await request.json()
    except Exception:
        return PlainTextResponse("Bad request", status_code=400)

    try:
        # CORRECT way for PTB v20+
        update = Update.de_json(data, tg_app.bot)

        await tg_app.update_queue.put(update)
    except Exception as e:
        log.exception("Failed to enqueue update: %s", e)
        return PlainTextResponse("Error", status_code=500)

    return PlainTextResponse("OK", status_code=200)
