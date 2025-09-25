import os
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import uvicorn

PORT = int(os.getenv("PORT", "10000"))

app = FastAPI()

@app.get("/", response_class=PlainTextResponse)
def root():
    return "OK"

@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "healthy"

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
