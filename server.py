# server.py
import logging
from fastapi import FastAPI, Request
from bot import application

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

app = FastAPI(title="Freelancer Bot API")

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook/{token}")
async def tg_webhook(token: str, request: Request):
    if token != application.bot.token:
        log.error("Invalid webhook token")
        return {"error": "unauthorized"}

    data = await request.json()
    await application.update_queue.put(data)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    log.info("Starting Telegram application...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
