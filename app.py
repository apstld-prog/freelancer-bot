from fastapi import FastAPI, Request
import httpx
from fastapi.responses import JSONResponse
from urllib.parse import quote

app = FastAPI()

@app.get("/")
@app.get("/api/pph")
async def proxy(request: Request):
    keyword = request.query_params.get("keyword", "")
    key = request.query_params.get("key", "")

    if key != "1211":
        return JSONResponse({"error": "Invalid key"}, status_code=403)

    search_url = f"https://www.peopleperhour.com/freelance-jobs?q={quote(keyword)}"
    print(f"[Proxy] Fetching: {search_url}")

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            return {"status": 200, "html": response.text}

    except httpx.HTTPStatusError as e:
        return {"status": e.response.status_code, "error": str(e)}
    except Exception as e:
        return {"status": 500, "error": str(e)}
