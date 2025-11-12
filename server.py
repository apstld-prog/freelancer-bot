import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from bot import build_application

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

app = FastAPI()
application = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


@app.on_event("startup")
async def on_startup():
    global application
    # FIX: build_application δεν είναι async
    application = build_application()
    logger.info("✅ FastAPI app started")
    logger.info(f"🔎 ENV check — PORT={os.getenv('PORT', '10000')} WORKER_INTERVAL={os.getenv('WORKER_INTERVAL')} KEYWORD_FILTER_MODE={os.getenv('KEYWORD_FILTER_MODE')}")


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
