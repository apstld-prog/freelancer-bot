import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from bot import build_application  # δεν αλλάζεις τίποτα άλλο στον bot
from telegram import Update

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("server")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

app = FastAPI()
tg_app = build_application()  # Application(...)

@app.on_event("startup")
async def startup() -> None:
    # Πολύ ΣΗΜΑΝΤΙΚΟ για webhook mode
    await tg_app.initialize()
    await tg_app.start()

    # Δηλώνουμε ρητά allowed_updates ώστε να έρχονται και /start (message)
    url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_URL")
    if not url:
        url = os.getenv("PRIMARY_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or ""
    if not url:
        log.warning("No external URL env set; using Render SERVICE URL if available.")
    webhook_url = f"{url}/webhook/{WEBHOOK_SECRET}".replace("//webhook", "/webhook")

    await tg_app.bot.delete_webhook(drop_pending_updates=True)
    await tg_app.bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=[
            "message",
            "edited_message",
            "callback_query",
            "chat_member",
            "my_chat_member"
        ],
    )
    log.info("Webhook set to %s", webhook_url)

@app.on_event("shutdown")
async def shutdown() -> None:
    await tg_app.stop()
    await tg_app.shutdown()

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "OK"

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid secret")
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return PlainTextResponse("OK")
