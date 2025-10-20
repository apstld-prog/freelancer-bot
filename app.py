from fastapi import FastAPI, Request
import httpx

app = FastAPI()

@app.get("/api/pph")
async def proxy(request: Request):
    keyword = request.query_params.get("keyword", "")
    key = request.query_params.get("key", "")

    if key != "1211":
        return {"error": "invalid key"}

    url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        return {"status": r.status_code, "html": r.text[:1000]}  # δείχνουμε μόνο τα πρώτα 1000 bytes
