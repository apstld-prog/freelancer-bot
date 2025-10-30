import logging
import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application
from bot import build_application

# ------------------------------------------------------
# Logging setup
# ------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

# ------------------------------------------------------
# FastAPI setup
# ------------------------------------------------------
app = FastAPI()

application: Application = build_application()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_URL = f"{os.getenv('RENDER_EXTERNAL_URL', 'https://freelancer-bot-ns7s.onrender.com')}/webhook/{WEBHOOK_SECRET}"

# ------------------------------------------------------
# Startup event
# ------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    logger.info("Application.initialize() starting")
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")
    logger.info("✅ Bot started via FastAPI")

# ------------------------------------------------------
# Shutdown event
# ------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application.shutdown() starting")
    await application.stop()
    await application.shutdown()
    logger.info("Application.shutdown() done")

# ------------------------------------------------------
# Webhook endpoint
# ------------------------------------------------------
@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def tg_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"Failed to process update: {e}", exc_info=True)
        return JSONResponse({"ok": False, "error": str(e)})

# ------------------------------------------------------
# Health check endpoint
# ------------------------------------------------------
@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Freelancer Bot server running"}

# ------------------------------------------------------
# Main entrypoint (Render fix)
# ------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server (Render mode)")
    uvicorn.run("server:app", host="0.0.0.0", port=10000, reload=False)
