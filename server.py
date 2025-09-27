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

# Build the PTB Application ONCE (no polling here)
tg_app = build_application()

PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")  # e.g. https://freelancer-bot-xxxx.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"

@app.get("/")
async def root():
    return JSONResponse({"ok": True, "service": "freelancer-bot"})

@app.on_event("startup")
async def on_startup():
    """
    Properly initialize and start the PTB Application so that process_update() can be used.
    Also, if PUBLIC_URL is set, reset & set the webhook to our endpoint.
    """
    # Initialize + Start PTB Application
    await tg_app.initialize()
    await tg_app.start()
    logger.info("PTB Application initialized and started (webhook mode).")

    # Optionally set webhook (if PUBLIC_URL provided)
    if PUBLIC_URL:
        try:
            url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.delete_webhook()
            await tg_app.bot.set_webhook(url=url, drop_pending_updates=True)
            logger.info("Webhook set to %s", url)
        except Exception as e:
            logger.warning("Failed to set webhook automatically: %s", e)
    else:
        logger.info("PUBLIC_URL not set — skipping automatic webhook setup.")

@app.on_event("shutdown")
async def on_shutdown():
    """
    Properly stop and shutdown the PTB Application.
    """
    try:
        await tg_app.stop()
        await tg_app.shutdown()
        logger.info("PTB Application stopped and shutdown.")
    except Exception as e:
        logger.warning("Error during PTB shutdown: %s", e)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Telegram will POST updates here. We parse the Update and hand it to PTB.
    We don't await processing to keep the endpoint fast; we schedule it on the event loop.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        update = telegram.Update.de_json(data, tg_app.bot)
    except Exception as e:
        logger.warning("Failed to parse Update: %s", e)
        raise HTTPException(status_code=400, detail="Bad Update payload")

    # Ensure app is initialized (defensive; should already be from startup hook)
    if not tg_app._initialized:  # PTB internal flag, safe check
        await tg_app.initialize()
        await tg_app.start()
        logger.info("PTB Application lazily initialized due to webhook hit.")

    # Process update asynchronously
    try:
        asyncio.create_task(tg_app.process_update(update))
    except Exception as e:
        logger.error("process_update error: %s", e)
        raise HTTPException(status_code=500, detail="process_update failed")

    return PlainTextResponse("ok", status_code=200)
