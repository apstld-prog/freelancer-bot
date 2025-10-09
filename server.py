import os
import logging
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application

from bot import build_application  # ΔΕΝ αλλάζουμε το bot.py – μόνο handlers/flows όπως συμφωνήσαμε

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

# ENV
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()  # π.χ. https://freelancer-bot-ns7s.onrender.com

# FastAPI app + Telegram Application
app = FastAPI()
application: Application = build_application()

@app.on_event("startup")
async def on_startup():
    # ΔΕΝ ξεκινάμε uvicorn εδώ. Μόνο webhook set.
    if WEBHOOK_BASE_URL:
        url = f"{WEBHOOK_BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        try:
            await application.bot.set_webhook(
                url=url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
            )
            log.info("Webhook set to %s", url)
        except Exception:
            log.exception("Failed to set webhook")
    log.info("✅ Bot started via FastAPI")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        data = await request.json()
    except Exception:
        log.exception("Invalid JSON body on webhook")
        return Response(status_code=200)

    # Λίγο logging για διάγνωση
    try:
        if "message" in data:
            msg = data["message"]
            log.info("Incoming message: chat=%s text=%s", msg.get("chat", {}).get("id"), msg.get("text"))
        if "callback_query" in data:
            cq = data["callback_query"]
            log.info("Incoming callback: from=%s data=%s", cq.get("from", {}).get("id"), cq.get("data"))
    except Exception:
        pass

    try:
        update = Update.de_json(data=data, bot=application.bot)
        await application.process_update(update)
    except Exception:
        log.exception("Failed to process update")
        # πάντα 200 στο Telegram
        return Response(status_code=200)

    return Response(status_code=200)
