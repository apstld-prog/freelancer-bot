import os
import logging
from fastapi import FastAPI, Request
from bot import application

log = logging.getLogger("server")
app = FastAPI()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = os.getenv("WEBHOOK_BASE_URL")
SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

WEBHOOK_URL = f"{BASE_URL}/{SECRET}"

@app.on_event("startup")
async def startup():
    log.info("Starting Telegram application...")
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(url=WEBHOOK_URL)
    await application.start()
    log.info("Webhook set and application started.")

@app.post("/{token}")
async def telegram_webhook(request: Request, token: str):
    if token != SECRET:
        return {"status": "ignored"}
    data = await request.json()
    await application.process_update(application.update_queue._parse_update(data))
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}
