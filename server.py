import uvicorn
from fastapi import FastAPI
from bot import build_application

app = FastAPI()
application = build_application()

@app.on_event("startup")
async def on_startup():
    print("✅ Bot started via FastAPI")

@app.get("/")
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=10000)
