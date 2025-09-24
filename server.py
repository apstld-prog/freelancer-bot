from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "service": "freelancer-bot"}

@app.get("/healthz")
def healthz():
    return {"ok": True}
