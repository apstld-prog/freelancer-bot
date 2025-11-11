import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

# Import the pre-built Telegram Application from your bot module
from bot import application

log = logging.getLogger("server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# Secrets & URLs
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "") or os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/{WEBHOOK_SECRET}"

app = FastAPI(title="Freelancer Alert Bot API", version="1.0.0")

# State flag: prevents updates before bot initialization
BOT_READY = False


@app.get("/")
async def root():
    # Simple landing page — Render health checks usually use GET /
    return {"status": "Freelancer Bot is running", "ready": BOT_READY}


# Health & readiness endpoints for explicit probes
@app.get("/healthz")
async def healthz():
    return PlainTextResponse("ok", status_code=200)

@app.get("/ready")
async def ready():
    return JSONResponse({"ready": BOT_READY}, status_code=200 if BOT_READY else 503)

# Some providers (or curious users/bots) hit the webhook with GET — return 200 to avoid 405 spam
@app.get(WEBHOOK_PATH)
async def webhook_get_probe():
    return PlainTextResponse("webhook endpoint (GET not used by Telegram)", status_code=200)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Receives Telegram webhook updates (POST only).
    """
    if not BOT_READY:
        return JSONResponse({"ok": False, "reason": "bot_not_ready"}, status_code=503)

    try:
        update = await request.json()
        # PTB v21+: application.process_update expects an Update object.
        # But PTB supports dicts here; it will coerce internally. If not, import Update and parse.
        await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse({"ok": False}, status_code=500)


@app.on_event("startup")
async def startup_event():
    """
    Initializes the Telegram application and sets the webhook.
    """
    global BOT_READY

    log.info("Starting Telegram webhook mode...")

    # 1) Init + start application
    await application.initialize()
    await application.start()

    # 2) Reset and set Telegram webhook
    base_url = WEBHOOK_BASE_URL.rstrip("/")
    full_hook = f"{base_url}{WEBHOOK_PATH}" if base_url else WEBHOOK_PATH

    # Ensure we always refresh the webhook target
    await application.bot.delete_webhook()
    await application.bot.set_webhook(url=full_hook)

    BOT_READY = True
    log.info(f"Webhook set: {full_hook}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Graceful shutdown of Telegram bot.
    We intentionally skip .stop()/.shutdown() to avoid PTB teardown issues
    during Render rolling restarts.
    """
    global BOT_READY

    BOT_READY = False
    log.info("Telegram app shutdown skipped (patched).")
    # If you ever need full teardown, uncomment:
    # await application.stop()
    # await application.shutdown()
