# server.py â€” FINAL FULL VERSION (Nov 2025)

import logging
from fastapi import FastAPI, Request
from bot import build_application

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

WEBHOOK_PATH = "/webhook/hook-secret-777"

# Build Telegram application
application = build_application()

app = FastAPI()


@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(f"https://freelancer-bot-ns7s.onrender.com{WEBHOOK_PATH}")
    log.info(f"âœ… Webhook set: https://freelancer-bot-ns7s.onrender.com{WEBHOOK_PATH}")


@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    await application.update_queue.put(data)
    return {"ok": True}


@app.on_event("shutdown")
async def on_shutdown():
    log.info("ðŸ›‘ Stopping bot...")
    await application.bot.delete_webhook()
    await application.stop()
    await application.shutdown()
    log.info("âœ… Bot stopped.")

