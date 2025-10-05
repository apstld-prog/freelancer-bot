import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from bot import build_application
from db import init_db, get_session, ensure_admin

log = logging.getLogger("server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "")

# DB bootstrap
init_db()
try:
    with get_session() as s:
        ensure_admin(s, ADMIN_ID)
except Exception as e:
    log.warning("ensure_admin skipped: %s", e)

app = FastAPI()
tg_app = build_application()

@app.get("/")
async def root():
    return {"ok": True, "name": "freelancer-bot", "webhook": f"/webhook/{WEBHOOK_SECRET}"}

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    try:
        update_json = await request.json()
        # PTB expects Update object; we pass raw dict via process_update
        await tg_app.update_queue.put(update_json)
        return PlainTextResponse("ok")
    except Exception as e:
        log.exception("webhook error: %s", e)
        raise HTTPException(500, "webhook error")

@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})
