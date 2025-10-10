
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update

from bot import build_application  # returns telegram.ext.Application (sync constructor)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Proper FastAPI lifespan handler (no deprecated @on_event).
    Builds the Telegram Application (sync), then initializes & starts it (async).
    Ensures graceful shutdown.
    """
    log.info("🚀 Starting bot application (lifespan)...")
    tg_app = build_application()            # DO NOT await here
    app.state.tg_app = tg_app
    # Start PTB application
    await tg_app.initialize()
    await tg_app.start()
    log.info("✅ Bot initialized and started.")
    try:
        yield
    finally:
        log.info("🛑 Stopping bot...")
        try:
            await tg_app.stop()
            await tg_app.shutdown()
        finally:
            log.info("✅ Bot stopped.")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "Freelancer Bot API running"}

@app.post("/webhook/{token}")
async def tg_webhook(token: str, request: Request):
    if token != os.getenv("HOOK_SECRET", "hook-secret-777"):
        return JSONResponse({"error": "unauthorized"}, status_code=403)
    try:
        data = await request.json()
        update = Update.de_json(data, app.state.tg_app.bot)
        await app.state.tg_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        log.exception("Failed to process webhook update: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
