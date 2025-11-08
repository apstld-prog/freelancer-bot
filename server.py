import logging
from fastapi import FastAPI, Request
from bot import application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI(title="Freelancer Bot API")

# Root endpoint — must return 200 for Render health checks
@app.get("/")
def root():
    return {"status": "ok"}

@app.head("/")
def head_root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"ok": True}

# Telegram Webhook
@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != application.bot.token:
        logger.error("Invalid webhook token")
        return {"error": "unauthorized"}

    data = await request.json()
    await application.update_queue.put(data)
    return {"ok": True}
