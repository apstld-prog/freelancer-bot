# server.py
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from bot import build_application
from db import ensure_schema  # FIX εδώ

logging.basicConfig(level=logging.INFO, format="%(asctime)s [server] %(levelname)s: %(message)s")
logger = logging.getLogger("server")

# Ensure DB tables
ensure_schema()

app = FastAPI()

tg_app = build_application()  # PTB Application (webhook)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    body = await request.json()
    await tg_app.update_queue.put(body)
    return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
