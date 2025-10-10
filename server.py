# server.py — FastAPI + PTB application with webhook
import os, logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

from bot import build_application

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
BASE_URL = (os.getenv("EXTERNAL_URL")
            or os.getenv("RENDER_EXTERNAL_URL")
            or os.getenv("WEBHOOK_BASE_URL"))

application: Application = build_application()

app = FastAPI()

@app.on_event("startup")
async def startup():
    if BASE_URL:
        url = f"{BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        await application.bot.set_webhook(url=url)
        log.info("Webhook set to %s", url)
    else:
        log.info("No BASE_URL detected; running in polling-less webhook mode (Render will call us).")

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
