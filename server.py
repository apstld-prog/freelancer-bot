import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from bot import build_application

app = FastAPI(title="freelancer-bot server")

# Create Telegram PTB application (no polling here; webhook handled elsewhere if needed)
tg_app = build_application()

@app.get("/")
async def root():
    return JSONResponse({"ok": True, "service": "freelancer-bot"})
