import logging
from fastapi import FastAPI, Request
from bot import build_application
from telegram import Update
import asyncio

app = FastAPI()
application = build_application()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


@app.on_event("startup")
async def startup_event():
    logger.info("Application.initialize() done")
    await application.initialize()
    await application.start()
    logger.info("✅ Bot started via FastAPI")


@app.post("/webhook/hook-secret-777")
async def tg_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
