import os
import logging
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application

from bot import build_application  # do not change bot.py structure per your request

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()  # e.g. https://freelancer-bot-ns7s.onrender.com

app = FastAPI(title="Freelancer Bot Server", version="1.0.0")

# Build a single global Application instance
application: Application = build_application()

_is_initialized = False
_is_started = False


@app.on_event("startup")
async def on_startup():
    """Initialize and start the Telegram Application, then set webhook."""
    global _is_initialized, _is_started
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

        log.info("✅ Bot started via FastAPI")

    except Exception:
        log.exception("Startup failed")


@app.on_event("shutdown")
async def on_shutdown():
    """Stop and shutdown the Telegram Application."""
    global _is_initialized, _is_started
    try:
        if _is_started:
            await application.stop()
            _is_started = False
            log.info("Application.stop() done")

        if _is_initialized:
            await application.shutdown()
            _is_initialized = False
            log.info("Application.shutdown() done")
    except Exception:
        log.exception("Shutdown failed")


# ---------- HEALTH ROUTES ----------

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/botok")
async def botok():
    """Render health check endpoint."""
    return {"ok": True, "service": "freelancer-bot", "status": "running"}

# ---------- TELEGRAM WEBHOOK ----------

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

    try:
        if "message" in data:
            msg = data["message"]
            log.info("Incoming message: chat=%s text=%s",
                     msg.get("chat", {}).get("id"),
                     msg.get("text"))
        if "callback_query" in data:
            cq = data["callback_query"]
            log.info("Incoming callback: from=%s data=%s",
                     cq.get("from", {}).get("id"),
                     cq.get("data"))
    except Exception:
        pass

    try:
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
