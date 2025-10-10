# server.py — FastAPI + PTB application with proper lifecycle (initialize/start/stop/shutdown)
import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

from bot import build_application

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
BASE_URL = (
    os.getenv("EXTERNAL_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or os.getenv("WEBHOOK_BASE_URL")
)

# Build the PTB application
application: Application = build_application()

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # IMPORTANT: initialize + start before processing updates
    await application.initialize()
    await application.start()

    if BASE_URL:
        url = f"{BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        await application.bot.set_webhook(url=url)
        log.info("Webhook set to %s", url)
    else:
        log.info("No BASE_URL detected; webhook not set (dev mode).")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await application.bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass
    await application.stop()
    await application.shutdown()

@app.get("/health")
async def health():
    return {"ok": True}

@app.post(f"/webhook/{{token}}")
async def telegram_webhook(token: str, request: Request):
    if token != WEBHOOK_SECRET:
        return {"ok": False, "error": "bad token"}
    data = await request.json()
    update = Update.de_json(data, application.bot)  # type: ignore
    await application.process_update(update)
    return {"ok": True}

# expose ASGI app for uvicorn
app = app
