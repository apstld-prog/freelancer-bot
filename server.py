# server.py — FastAPI + Telegram webhook, fully fixed

import os
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from bot import build_application

log = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if render_url:
        WEBHOOK_URL = render_url
    else:
        WEBHOOK_URL = ""

tg_app = None  # global


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_app

    log.info("LIFESPAN: startup — building Telegram application...")
    tg_app = build_application()

    # FIRST: initialize()
    log.info("Initializing Telegram application...")
    await tg_app.initialize()
    log.info("Initialized OK.")

    # Set webhook
    if WEBHOOK_URL:
        wh = f"{WEBHOOK_URL.rstrip('/')}/telegram/{BOT_TOKEN}"
        try:
            await tg_app.bot.set_webhook(wh)
            log.info("Webhook set OK: %s", wh)
        except Exception as e:
            log.exception("Webhook error: %s", e)

    # THEN: start()
    log.info("Starting Telegram application...")
    await tg_app.start()
    log.info("Telegram application started.")

    try:
        yield
    finally:
        # shutdown
        log.info("LIFESPAN: shutdown — stopping Telegram application...")
        try:
            await tg_app.stop()
        except Exception as e:
            log.exception("Stop error: %s", e)
        log.info("Telegram app stopped.")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return PlainTextResponse("Freelancer Alert Bot web service is up.", status_code=200)


@app.post(f"/telegram/{{token}}")
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
        update = tg_app._update_cls.de_json(data, tg_app.bot)  # type: ignore
        await tg_app.update_queue.put(update)
    except Exception as e:
        log.exception("Failed to enqueue update: %s", e)
        return PlainTextResponse("Error", status_code=500)

    return PlainTextResponse("OK", status_code=200)
