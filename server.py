# server.py — FastAPI entrypoint for Render (web service)
# EN-only code as requested

import os
import logging
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("server")

app = FastAPI(title="Freelancer Alert Bot — Web")

@app.on_event("startup")
async def on_startup():
    logger.info("✅ FastAPI app started")
    logger.info("🔎 ENV check — PORT=%s WORKER_INTERVAL=%s KEYWORD_FILTER_MODE=%s",
                os.getenv("PORT"), os.getenv("WORKER_INTERVAL"), os.getenv("KEYWORD_FILTER_MODE"))

@app.get("/", response_class=PlainTextResponse)
async def root():
    """Health endpoint used by Render; returns 200 OK."""
    return "OK"

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    """Secondary health endpoint."""
    return "OK"

@app.get("/version", response_class=JSONResponse)
async def version():
    return {
        "status": "ok",
        "commit": os.getenv("RENDER_GIT_COMMIT", ""),
        "branch": os.getenv("RENDER_GIT_BRANCH", ""),
    }

# Optional: favicon to avoid noisy 404s in logs
@app.get("/favicon.ico", response_class=PlainTextResponse)
async def favicon():
    return ""
