import os
import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import telegram

from bot import build_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s [server] %(levelname)s: %(message)s")
logger = logging.getLogger("server")

app = FastAPI(title="freelancer-bot server")

# Build PTB Application (ΔΕΝ κάνουμε polling εδώ)
tg_app = build_application()

# --------- Basic health ---------
@app.get("/")
async def root():
    return JSONResponse({"ok": True, "service": "freelancer-bot"})

# --------- Webhook setup ---------
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")  # π.χ. https://freelancer-bot-ns7s.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"

@app.on_event("startup")
async def setup_webhook_if_configured():
    # Αν έχεις PUBLIC_URL, θα κάνουμε αυτόματο set webhook στο startup.
    if not PUBLIC_URL:
        logger.info("PUBLIC_URL not set — skipping automatic webhook setup.")
        return
    try:
        url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
        # Πρώτα καθαρίζουμε τυχόν παλιό webhook και μετά ορίζουμε νέο
        await tg_app.bot.delete_webhook()
        await tg_app.bot.set_webhook(url=url, drop_pending_updates=True)
        logger.info("Webhook set to %s", url)
    except Exception as e:
        logger.warning("Failed to set webhook automatically: %s", e)

# --------- Telegram webhook endpoint ---------
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        update = telegram.Update.de_json(data, tg_app.bot)
    except Exception as e:
        logger.warning("Failed to parse Update: %s", e)
        raise HTTPException(status_code=400, detail="Bad Update payload")

    # Επεξεργασία update από το PTB
    try:
        # Δεν μπλοκάρουμε το request — τρέχουμε την επεξεργασία ασύγχρονα
        asyncio.create_task(tg_app.process_update(update))
    except Exception as e:
        logger.error("process_update error: %s", e)
        raise HTTPException(status_code=500, detail="process_update failed")

    return PlainTextResponse("ok", status_code=200)
