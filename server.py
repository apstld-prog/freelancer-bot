
import os, logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from bot import build_application
from config import WEBHOOK_SECRET, WEBHOOK_BASE

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

app = FastAPI()
application = build_application()

@app.on_event("startup")
async def on_startup():
    await application.initialize()
    base = WEBHOOK_BASE.rstrip("/") if WEBHOOK_BASE else os.getenv("RENDER_EXTERNAL_URL","").rstrip("/")
    if base:
        hook_url = f"{base}/{WEBHOOK_SECRET}"
        await application.bot.set_webhook(url=hook_url)
        log.info(f"✅ Telegram webhook set: {hook_url}")
    await application.start()
    log.info("✅ FastAPI app started")
    log.info(f"🔎 ENV check — PORT={os.getenv('PORT')} WORKER_INTERVAL={os.getenv('WORKER_INTERVAL')} KEYWORD_FILTER_MODE={os.getenv('KEYWORD_FILTER_MODE')}")

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()

@app.get("/")
async def root():
    return {"status":"ok"}

@app.post(f"/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})
