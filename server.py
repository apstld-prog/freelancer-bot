import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application

from bot import build_application  # do not change bot.py structure per your request

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()  # e.g. https://freelancer-bot-ns7s.onrender.com

# Build a single global Application instance 
application: Application = build_application()

# Flags to avoid double init/stop
_is_initialized = False
_is_started = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler = replacement for @app.on_event("startup"/"shutdown").

    Κάνει:
    - initialize + start το Telegram Application
    - set webhook
    - στο τέλος κάνει stop + shutdown
    """
    global _is_initialized, _is_started

    # ---------- STARTUP ----------
    try:
        if not _is_initialized:
            await application.initialize()
            _is_initialized = True
            log.info("Application.initialize() done")

        if not _is_started:
            await application.start()
            _is_started = True
            log.info("Application.start() done")

        if WEBHOOK_BASE_URL:
            url = f"{WEBHOOK_BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
            await application.bot.set_webhook(
                url=url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
            )
            log.info("Webhook set to %s", url)

        log.info("✅ Bot started via FastAPI lifespan")

    except Exception:
        log.exception("Startup (lifespan) failed")

    # Δίνουμε τον έλεγχο στην FastAPI
    yield

    # ---------- SHUTDOWN ----------
    try:
        if _is_started:
            await application.stop()
            _is_started = False
            log.info("Application.stop() done")

        if _is_initialized:
            await application.shutdown()
            _is_initialized = False
            log.info("Application.shutdown() done")

        log.info("✅ Bot stopped via FastAPI lifespan")

    except Exception:
        log.exception("Shutdown (lifespan) failed")


# Δημιουργούμε το app με lifespan (χωρίς @app.on_event)
app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok"}


@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    """Telegram webhook endpoint."""
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        data = await request.json()
    except Exception:
        log.exception("Invalid JSON body on webhook")
        return Response(status_code=200)

    # Light logging for diagnostics (do not log PII)
    try:
        if "message" in data:
            msg = data["message"]
            log.info(
                "Incoming message: chat=%s text=%s",
                msg.get("chat", {}).get("id"),
                msg.get("text"),
            )
        if "callback_query" in data:
            cq = data["callback_query"]
            log.info(
                "Incoming callback: from=%s data=%s",
                cq.get("from", {}).get("id"),
                cq.get("data"),
            )
    except Exception:
        # Δεν μας νοιάζει αν αποτύχει το logging
        pass

    try:
        # Safety net: αν για κάποιο λόγο δεν είναι initialized/started, το
        # ξανακάνουμε εδώ (idempotent χάρη στα flags).
        global _is_initialized, _is_started
        if not _is_initialized:
            await application.initialize()
            _is_initialized = True
            log.info("Re-initialize Application in webhook")

        if not _is_started:
            await application.start()
            _is_started = True
            log.info("Re-start Application in webhook")

        update = Update.de_json(data=data, bot=application.bot)
        await application.process_update(update)

    except Exception:
        log.exception("Failed to process update")
        return Response(status_code=200)

    return Response(status_code=200)
