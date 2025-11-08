from fastapi import FastAPI, Request
from telegram import Update
from bot import application

app = FastAPI()

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

