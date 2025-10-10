import os
import logging
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application
from bot import build_application
from config import WEBHOOK_SECRET as CFG_SECRET  # fallback if needed

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", CFG_SECRET or "hook-secret-777").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", os.getenv("WEBHOOK_URL", "")).strip()

app = FastAPI()

# Singleton telegram Application
application: Application = build_application()
_is_initialized = False
_is_started = False

async def _ensure_started():
    global _is_initialized, _is_started
    if not _is_initialized:
        await application.initialize()
        _is_initialized = True
        log.info("Application.initialize() done")
    if not _is_started:
        await application.start()
        _is_started = True
        log.info("Application.start() done")

async def _ensure_webhook():
    if not WEBHOOK_BASE_URL:
        log.warning("WEBHOOK_BASE_URL not set — webhook will not be configured.")
        return
    target = f"{WEBHOOK_BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    try:
        info = await application.bot.get_webhook_info()
        if info.url != target:
            await application.bot.set_webhook(url=target, max_connections=100, drop_pending_updates=True)
            log.info("Webhook set to %s", target)
        else:
            log.info("Webhook already set to %s", target)
    except Exception:
        log.exception("Failed to set webhook")

@app.on_event("startup")
async def on_startup():
    try:
        await _ensure_started()
        await _ensure_webhook()
        log.info("✅ Bot is ready")
    except Exception:
        log.exception("Startup failed")

@app.on_event("shutdown")
async def on_shutdown():
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
        log.exception("Shutdown error")

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_started()
    data = await request.json()
    try:
        update = Update.de_json(data=data, bot=application.bot)
        await application.process_update(update)
    except Exception:
        log.exception("Failed to process update")
        # Always 200 to avoid Telegram retry storms; errors go to logs
        return Response(status_code=200)
    return Response(status_code=200)
