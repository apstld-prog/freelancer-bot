
# server.py — Full Webhook FastAPI server (no polling)

import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from telegram import Update
from telegram.ext import Application

from bot import application  # your bot.py builds `application`

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = FastAPI()

@app.get("/")
async def root():
    return HTMLResponse("<h3>Freelancer Alert Bot running</h3>")

@app.post(f"/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})

@app.on_event("startup")
async def startup_event():
    logging.info("🚀 FastAPI startup…")
    try:
        await application.bot.delete_webhook()
        result = await application.bot.set_webhook(
            url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{WEBHOOK_SECRET}"
        )
        logging.info(f"🌍 Webhook set → {result}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("🔻 Shutting down bot")
    await application.shutdown()
