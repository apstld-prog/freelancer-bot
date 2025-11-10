import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bot import application

log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_PATH = f"/{WEBHOOK_SECRET}"

app = FastAPI()

# State flag: prevents updates before bot initialization
BOT_READY = False


@app.get("/")
async def root():
    return {"status": "Freelancer Bot is running"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Receives Telegram webhook updates.
    """
    if not BOT_READY:
        return JSONResponse({"ok": False, "reason": "bot_not_ready"})

    try:
        update = await request.json()
        await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse({"ok": False})


@app.on_event("startup")
async def startup_event():
    """
    Initializes the Telegram application and sets the webhook.
    """
    global BOT_READY

    log.info("Starting Telegram webhook mode...")

    # Initialization sequence
    await application.initialize()
    await application.start()

    # Reset and set Telegram webhook
    base_url = os.getenv("WEBHOOK_BASE_URL", "")
    await application.bot.delete_webhook()
    await application.bot.set_webhook(url=base_url + WEBHOOK_PATH)

    BOT_READY = True
    log.info(f"Webhook set: {base_url + WEBHOOK_PATH}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Graceful shutdown of Telegram bot.
    """
    global BOT_READY

    log.info("Shutting down Telegram application...")
    BOT_READY = False

    await application.stop()
    await application.shutdown()
