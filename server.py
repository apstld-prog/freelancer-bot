import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application
from db import init_db
from bot import build_application  # το build_application φτιάχνει PTB Application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

WEBHOOK_PATH = "/webhook/hook-secret-777"
PUBLIC_URL = os.getenv("PUBLIC_URL", "")  # π.χ. https://freelancer-bot-ns7s.onrender.com

app = FastAPI()
tg_app: Application = build_application()


@app.on_event("startup")
async def on_startup():
    # --- Ensure DB tables exist ---
    try:
        init_db()
        logger.info("DB schema ensured (create_all).")
    except Exception as e:
        logger.warning("DB init failed (non-fatal): %s", e)

    # --- Init & start Telegram bot ---
    await tg_app.initialize()
    await tg_app.start()
    logger.info("PTB Application initialized and started (webhook mode).")

    if PUBLIC_URL:
        try:
            url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.delete_webhook()
            await tg_app.bot.set_webhook(url=url, drop_pending_updates=True)
            logger.info("Webhook set to %s", url)
        except Exception as e:
            logger.warning("Failed to set webhook automatically: %s", e)
    else:
        logger.info("PUBLIC_URL not set — skipping webhook setup.")


@app.on_event("shutdown")
async def on_shutdown():
    await tg_app.stop()
    await tg_app.shutdown()
    logger.info("PTB Application stopped.")


@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid JSON"})

    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "ok"}
