from fastapi import FastAPI
from bot import application

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "message": "Freelancer Bot API running"}

# ✅ Telegram webhook endpoint
from fastapi import Request
import json

@app.post("/")
async def telegram_webhook(req: Request):
    data = await req.body()
    update = json.loads(data.decode("utf-8"))
    await application.update_queue.put(update)
    return {"ok": True}

