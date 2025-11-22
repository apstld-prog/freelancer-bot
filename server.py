# server.py — FastAPI + Telegram webhook, single event loop, no "Application exited early"

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

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # π.χ. https://freelancer-bot-ns7s.onrender.com
if not WEBHOOK_URL:
    # fallback για Render: παίρνει RENDER_EXTERNAL_URL αν υπάρχει
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        WEBHOOK_URL = render_url
    else:
        # τελείως fallback: δεν σπάει αλλά δεν στήνει webhook
        WEBHOOK_URL = ""

# Το application του telegram (θα το φτιάξουμε στο lifespan)
tg_app = None  # type: ignore[assignment]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Νέος, σωστός τρόπος (lifespan) αντί για @app.on_event("startup"/"shutdown").
    ΕΔΩ:
      - build_application()
      - set webhook
      - start tg_app.start()
    Στο τέλος:
      - stop tg_app.stop()
    """
    global tg_app

    log.info("LIFESPAN: startup — building Telegram application...")
    tg_app = build_application()

    # Αν έχουμε WEBHOOK_URL, στήνουμε webhook, αλλιώς τρέχει σε polling-like mode αλλά χωρίς να κρασάρει.
    if WEBHOOK_URL:
        wh_url = f"{WEBHOOK_URL.rstrip('/')}/telegram/{BOT_TOKEN}"
        log.info("Setting Telegram webhook to %s", wh_url)
        try:
            await tg_app.bot.set_webhook(wh_url)
            log.info("Webhook set OK.")
        except Exception as e:
            log.exception("Failed to set webhook: %s", e)

    # Ξεκινάμε το telegram app (χωρίς δεύτερο event loop)
    log.info("Starting Telegram application (tg_app.start()) ...")
    await tg_app.start()
    log.info("Telegram application started.")

    try:
        yield
    finally:
        # Shutdown
        log.info("LIFESPAN: shutdown — stopping Telegram application...")
        if tg_app is not None:
            try:
                await tg_app.stop()
            except Exception as e:
                log.exception("Error while stopping Telegram application: %s", e)
        log.info("Telegram application stopped. Lifespan finished.")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return PlainTextResponse("Freelancer Alert Bot web service is up.", status_code=200)


@app.post(f"/telegram/{{token}}")
async def telegram_webhook(token: str, request: Request):
    """
    Webhook endpoint που δέχεται updates από το Telegram και τα στέλνει
    στο application του python-telegram-bot.
    """
    global tg_app

    if token != BOT_TOKEN:
        return PlainTextResponse("Invalid token", status_code=403)

    if tg_app is None:
        return PlainTextResponse("Telegram application not ready", status_code=503)

    try:
        data = await request.json()
    except Exception:
        return PlainTextResponse("Bad request", status_code=400)

    try:
        await tg_app.update_queue.put(tg_app._update_cls.de_json(data, tg_app.bot))  # type: ignore[attr-defined]
    except Exception as e:
        log.exception("Failed to put update in queue: %s", e)
        return PlainTextResponse("Error", status_code=500)

    return PlainTextResponse("OK", status_code=200)
