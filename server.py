import logging
from fastapi import FastAPI
from bot import application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI(title="Freelancer Bot API")

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: dict):
    if token != application.bot.token:
        return {"error": "unauthorized"}
    await application.update_queue.put(request)
    return {"ok": True}
