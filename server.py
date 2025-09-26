import os
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/")
def root():
    return {"service": "freelancer-bot", "status": "running"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
