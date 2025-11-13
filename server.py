import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from bot import build_application

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = FastAPI()
application = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


@app.on_event("startup")
async def on_startup():
    global application
    application = build_application()

    # -----------------------------
    # SET WEBHOOK (CRITICAL)
    # -----------------------------
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        raise RuntimeError("RENDER_EXTERNAL_HOSTNAME is missing. Webhook cannot be set.")

    webhook_url = f"https://{hostname}/{WEBHOOK_SECRET}"

    try:
        await application.bot.delete_webhook()
        ok = await application.bot.set_webhook(webhook_url)

        logger.info("==================================================")
        logger.info(f"🌍 Webhook URL set → {webhook_url}")
        logger.info(f"Webhook result: {ok}")
        logger.info("==================================================")
    except Exception as e:
        logger.error(f"❌ Failed to set webhook: {e}")

    logger.info("✅ FastAPI app started")
    logger.info(
        f"🔎 ENV check — PORT={os.getenv('PORT', '10000')} "
        f"WORKER_INTERVAL={os.getenv('WORKER_INTERVAL')} "
        f"KEYWORD_FILTER_MODE={os.getenv('KEYWORD_FILTER_MODE')}"
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h3>✅ Freelancer Alert Bot is running properly.</h3>"


@app.post(f"/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        if application:
            await application.update_queue.put(update)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)
