import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import uvicorn
from telegram import Update

from bot import build_application

PORT = int(os.getenv("PORT", "10000"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "")  # π.χ. https://freelancer-bot-ns7s.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-123")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [server] %(levelname)s: %(message)s")
logger = logging.getLogger("server")

app = FastAPI()
tg_app = build_application()  # PTB Application (no polling)

@app.on_event("startup")
async def _startup():
    await tg_app.initialize()
    await tg_app.start()
    # set webhook
    if not PUBLIC_URL:
        logger.warning("PUBLIC_URL is not set; webhook will NOT be set.")
    else:
        url = f"{PUBLIC_URL}/webhook/{WEBHOOK_SECRET}"
        await tg_app.bot.set_webhook(url, drop_pending_updates=True)
        logger.info(f"Webhook set to: {url}")

@app.on_event("shutdown")
async def _shutdown():
    try:
        await tg_app.bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass
    await tg_app.stop()
    await tg_app.shutdown()

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "OK"

@app.post(f"/webhook/{{secret}}")
async def telegram_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(403, "forbidden")
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
