import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from bot import build_application
from db import init_db, ensure_admin

log = logging.getLogger("server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "")

init_db()
ensure_admin(__import__("db").db.get_session(), ADMIN_ID)  # lazy get_session import

app = FastAPI()
tg_app = build_application()  # PTB Application already initialized for webhook mode

@app.get("/")
async def root():
    return {"ok": True, "name": "freelancer-bot", "webhook": f"/webhook/{WEBHOOK_SECRET}"}

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    try:
        body = await request.body()
        await tg_app.update_queue.put(body)  # PTB HTTP webhook: we pass raw JSON to queue
        return PlainTextResponse("ok")
    except Exception as e:
        log.exception("webhook error: %s", e)
        raise HTTPException(500, "webhook error")

@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})
