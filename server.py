# server.py
from __future__ import annotations
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application

from bot import build_application
from admin_feedsstatus import register_feedsstatus

logging.basicConfig(level=logging.INFO, format="INFO:%(name)s:%(message)s")
log = logging.getLogger("server")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
PRIMARY_URL = os.getenv("PRIMARY_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")

app = FastAPI()
tg_app: Application = build_application()

# register the admin-only /feedsstatus
register_feedsstatus(tg_app)

@app.on_event("startup")
async def _startup():
    await tg_app.initialize()
    await tg_app.start()
    if PRIMARY_URL and BOT_TOKEN:
        url = f"{PRIMARY_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        try:
            await tg_app.bot.delete_webhook()
            await tg_app.bot.set_webhook(url=url, allowed_updates=Update.ALL_TYPES)
            log.info(f"Webhook set to {url}")
        except Exception as e:
            log.warning(f"Webhook set failed: {e}")

@app.on_event("shutdown")
async def _shutdown():
    try:
        await tg_app.stop()
        await tg_app.shutdown()
    except Exception as e:
        log.warning(f"Shutdown issue: {e}")

@app.get("/")
async def root():
    return {"ok": True, "service": "freelancer-bot", "webhook": bool(PRIMARY_URL)}

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}
