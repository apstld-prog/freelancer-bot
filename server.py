import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application

from bot import build_application

# Logging setup
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

# FastAPI app with lifespan handlers instead of deprecated on_event
app = FastAPI()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {"status": "Freelancer Bot API running"}

@app.post("/webhook/{token}")
async def tg_webhook(token: str, request: Request):
    if token != os.getenv("HOOK_SECRET", "hook-secret-777"):
        return JSONResponse({"error": "unauthorized"}, status_code=403)
    try:
        data = await request.json()
        update = Update.de_json(data, app.tg_app.bot)
        await app.tg_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        log.exception("Failed to process webhook update: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

# Lifespan event handler (replaces deprecated on_event)
@app.on_event("startup")
async def startup_event():
    log.info("🚀 Starting bot application...")
    tg_app = await build_application()
    app.tg_app = tg_app
    log.info("✅ Bot initialized successfully.")

@app.on_event("shutdown")
async def shutdown_event():
    log.info("🛑 Shutting down bot...")
    if hasattr(app, "tg_app"):
        await app.tg_app.shutdown()

# Ensure Render port binding
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
