import os
import uvicorn
from fastapi import FastAPI, Request, Response
from telegram.ext import Application
from bot import build_application

app = FastAPI()
application: Application = build_application()

@app.on_event("startup")
async def on_startup():
    print("✅ Bot started via FastAPI")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    return Response(status_code=200)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")), reload=False)
