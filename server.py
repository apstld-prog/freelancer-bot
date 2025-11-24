# server.py — FastAPI + Telegram webhook + SKY PROXY (FINAL 2025)

import os
import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

import httpx
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

    # Initialize
    log.info("Initializing Telegram application...")
    await tg_app.initialize()
    log.info("Initialized OK.")

    # Set webhook
    if WEBHOOK_URL:
        wh_url = f"{WEBHOOK_URL.rstrip('/')}/telegram/{BOT_TOKEN}"
        try:
            await tg_app.bot.set_webhook(wh_url)
            log.info("Webhook set OK: %s", wh_url)
        except Exception as e:
            log.exception("Webhook error: %s", e)

    # Start
    log.info("Starting Telegram application...")
    await tg_app.start()
    log.info("Telegram application started.")

    # Enter lifespan
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
# SKYWALKER PROXY (bypass Cloudflare permanently)
# ---------------------------------------------------------------------
@app.get("/skywalker_proxy", tags=["proxy"])
async def skywalker_proxy():
    """
    Server-side fetch of Skywalker XML feed to bypass Cloudflare.
    The worker will read from this endpoint instead of the original feed.
    """
    FEED_URL = "https://www.skywalker.gr/jobs/feed"

    try:
        r = httpx.get(
            FEED_URL,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml,application/xml,text/xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.skywalker.gr/",
            }
        )
        r.raise_for_status()
    except Exception as e:
        return Response(f"<error>{str(e)}</error>", media_type="application/xml")

    return Response(r.text, media_type="application/xml")


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
        update = Update.de_json(data, tg_app.bot)
        await tg_app.update_queue.put(update)
    except Exception as e:
        log.exception("Failed to enqueue update: %s", e)
        return PlainTextResponse("Error", status_code=500)

    return PlainTextResponse("OK", status_code=200)
