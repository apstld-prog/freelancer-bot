import asyncio
import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application
from bot import build_application
from db_events import ensure_feed_events_schema
from workers.worker_freelancer import process_jobs as freelancer_worker
from workers.worker_pph import process_jobs as pph_worker
from workers.worker_skywalker import process_jobs as skywalker_worker

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
# Async startup
# ------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    logger.info("⚙️ Initializing Freelancer Bot application...")
    ensure_feed_events_schema()

    # Start the Telegram bot
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook set to {WEBHOOK_URL}")

    # Launch background workers (non-blocking)
    interval = int(os.getenv("WORKER_INTERVAL", 120))
    logger.info(f"🚀 Starting background workers every {interval}s...")

    async def run_freelancer():
        while True:
            try:
                await freelancer_worker()
            except Exception as e:
                logger.error(f"[Freelancer Worker Error] {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def run_pph():
        while True:
            try:
                await pph_worker()
            except Exception as e:
                logger.error(f"[PPH Worker Error] {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def run_skywalker():
        while True:
            try:
                await skywalker_worker()
            except Exception as e:
                logger.error(f"[Skywalker Worker Error] {e}", exc_info=True)
            await asyncio.sleep(interval)

    # Create async background tasks
    asyncio.create_task(run_freelancer())
    asyncio.create_task(run_pph())
    asyncio.create_task(run_skywalker())

    logger.info("✅ All background workers started successfully.")

# ------------------------------------------------------
# Shutdown
# ------------------------------------------------------
@app.on_event("shutdown")
async def on_shutdown():
    logger.info("🧹 Shutting down application...")
    await application.stop()
    await application.shutdown()
    logger.info("✅ Application shutdown complete.")

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
    return {"status": "ok", "message": "Freelancer Bot is running with workers."}

# ------------------------------------------------------
# Main entrypoint (for local testing or Render manual run)
# ------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server (Render unified mode)")
    uvicorn.run("server:app", host="0.0.0.0", port=10000, reload=False)
