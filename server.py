import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from bot import build_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI()
application = build_application()

@app.on_event("startup")
async def startup_event():
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook/hook-secret-777"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")
    logger.info("✅ Bot started via FastAPI")

@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != "hook-secret-777":
        return {"status": "forbidden"}
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
