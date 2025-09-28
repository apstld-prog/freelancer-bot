# server.py
import os
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.error import TelegramError

from bot import build_application
from db import ensure_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [server] %(levelname)s: %(message)s")
logger = logging.getLogger("server")

# ------------ Config ------------
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_URL    = os.getenv("WEBHOOK_URL", "").strip()      # full URL (recommended)
WEBHOOK_BASE   = os.getenv("WEBHOOK_BASE", "").strip()     # e.g. https://your-app.onrender.com
PORT           = int(os.getenv("PORT", "10000"))

# ------------ Helpers ------------
def compute_webhook_url() -> str:
    """Resolve the final webhook URL."""
    if WEBHOOK_URL:
        return WEBHOOK_URL
    base = WEBHOOK_BASE.rstrip("/")
    if not base:
        # Fallback to Render-style guess (not always reliable). Prefer WEBHOOK_URL!
        raise RuntimeError(
            "WEBHOOK_URL is not set. Set WEBHOOK_URL to your public webhook endpoint, "
            "e.g. https://freelancer-bot-ns7s.onrender.com/webhook/hook-secret-777"
        )
    return f"{base}/webhook/{WEBHOOK_SECRET}"

# ------------ FastAPI + PTB lifecycle ------------
app = FastAPI()
tg_app = build_application()  # PTB Application

@asynccontextmanager
async def lifespan(app_: FastAPI):
    # Ensure DB tables
    ensure_schema()
    # Init & start Telegram Application (webhook mode)
    await tg_app.initialize()
    # Always set webhook explicitly (delete first)
    try:
        await tg_app.bot.delete_webhook(drop_pending_updates=True)
    except TelegramError as e:
        logger.warning("delete_webhook failed: %s", e)
    webhook_url = compute_webhook_url()
    try:
        await tg_app.bot.set_webhook(url=webhook_url)
        logger.info("Webhook set to %s", webhook_url)
    except TelegramError as e:
        logger.error("set_webhook failed: %s", e)
        raise
    await tg_app.start()
    logger.info("PTB Application started (webhook mode).")
    try:
        yield
    finally:
        # Graceful shutdown
        await tg_app.stop()
        await tg_app.shutdown()
        logger.info("PTB Application stopped.")

app.router.lifespan_context = lifespan

# ------------ Routes ------------
@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    try:
        update = Update.de_json(data, tg_app.bot)
        await tg_app.process_update(update)
    except Exception as e:
        logger.exception("Failed to process update: %s", e)
        # Do not retry on Telegram's side—ack with 200 and log the error
        return JSONResponse({"status": "err", "detail": str(e)}, status_code=200)

    return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
