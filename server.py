import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bot import application

log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_PATH = f"/{WEBHOOK_SECRET}"

app = FastAPI()


@app.get("/")
async def root():
    return {"status": "Freelancer Bot is running"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse({"ok": False})


@app.on_event("startup")
async def startup_event():
    log.info("Starting Telegram webhook mode...")

    # ✅ REQUIRED: initialize and start the Application
    await application.initialize()
    await application.start()

    # ✅ Reset webhook
    await application.bot.delete_webhook()
    await application.bot.set_webhook(
        url=os.getenv("WEBHOOK_BASE_URL") + WEBHOOK_PATH
    )

    log.info(f"✅ Webhook set: {os.getenv('WEBHOOK_BASE_URL') + WEBHOOK_PATH}")


@app.on_event("shutdown")
async def shutdown_event():
    log.info("Shutting down Telegram application...")
    await application.stop()
    await application.shutdown()
