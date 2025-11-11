# server.py — FastAPI entrypoint with Telegram webhook (PTB v20+)
# EN-only code

import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from telegram import Update

# Your bot factory must exist and keep the same signature:
# from bot import build_application
try:
    from bot import build_application  # returns telegram.ext.Application
except Exception as e:
    raise RuntimeError("Could not import build_application() from bot.py") from e

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("server")

app = FastAPI(title="Freelancer Alert Bot — Web")

# Global Telegram Application instance
tg_app = build_application()

# Webhook path (must match what Telegram hits)
WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "/hook-secret-777")

def _external_base_url() -> str:
    # Prefer Render-provided URL, fallback to env, then empty string
    return (
        os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("EXTERNAL_BASE_URL")
        or ""
    ).rstrip("/")

@app.on_event("startup")
async def on_startup() -> None:
    log.info("✅ FastAPI started")
    log.info(
        "🔎 ENV — PORT=%s WORKER_INTERVAL=%s KEYWORD_FILTER_MODE=%s RENDER_EXTERNAL_URL=%s",
        os.getenv("PORT"), os.getenv("WORKER_INTERVAL"),
        os.getenv("KEYWORD_FILTER_MODE"), os.getenv("RENDER_EXTERNAL_URL"),
    )
    # Initialize and start PTB application
    await tg_app.initialize()
    await tg_app.start()

    base = _external_base_url()
    if base:
        url = f"{base}{WEBHOOK_PATH}"
        await tg_app.bot.set_webhook(url=url)
        log.info("✅ Telegram webhook set to %s", url)
    else:
        log.warning("⚠️ RENDER_EXTERNAL_URL not set — webhook not configured")

@app.on_event("shutdown")
async def on_shutdown() -> None:
    # Gracefully stop PTB application
    await tg_app.stop()
    await tg_app.shutdown()
    log.info("👋 Shutdown complete")

# ---------- Health Endpoints ----------

@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    """Primary health check (Render can call GET here)."""
    return "OK"

@app.head("/", response_class=PlainTextResponse)
async def root_head() -> str:
    """HEAD also returns 200 to avoid 405s in logs."""
    return ""

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "OK"

@app.get("/version", response_class=JSONResponse)
async def version() -> dict:
    return {
        "status": "ok",
        "commit": os.getenv("RENDER_GIT_COMMIT", ""),
        "branch": os.getenv("RENDER_GIT_BRANCH", ""),
    }

# ---------- Telegram Webhook ----------

@app.post(WEBHOOK_PATH, response_class=PlainTextResponse)
async def telegram_webhook(request: Request) -> str:
    """Receives Telegram updates and hands them to PTB."""
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return "OK"
