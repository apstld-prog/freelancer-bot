from fastapi import FastAPI, Query
import httpx
from bs4 import BeautifulSoup

API_KEY = "1211"

app = FastAPI(title="PeoplePerHour Proxy API")

@app.get("/api/pph")
def get_pph_jobs(keyword: str = Query(...), limit: int = 10, key: str = Query("")):
    """Proxy API για PeoplePerHour - προστατευμένο με key"""
    if key != API_KEY:
        return {"error": "Unauthorized", "data": []}

    url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            r = client.get(url)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "data": []}

        soup = BeautifulSoup(r.text, "html.parser")
        jobs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/freelance-jobs/" in href and not href.endswith("/freelance-jobs"):
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    jobs.append({
                        "title": title,
                        "url": f"https://www.peopleperhour.com{href}" if not href.startswith("http") else href
                    })
            if len(jobs) >= limit:
                break

        return {"keyword": keyword, "count": len(jobs), "data": jobs}

    except Exception as e:
        return {"error": str(e), "data": []}


@app.get("/health")
def health():
    """Health check για Render / UptimeRobot"""
    return {"status": "ok"}
