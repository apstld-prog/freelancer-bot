import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone

logger = logging.getLogger("platform_skywalker")

BASE_URL = "https://www.skywalker.gr/elGR/aggelies"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "el,en;q=0.9",
    "Referer": "https://www.google.com/",
}

async def fetch_skywalker_jobs(keyword: str):
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=False) as client:
            r = await client.get(BASE_URL, params={"keyword": keyword})
            if r.status_code != 200:
                logger.warning(f"[Skywalker] Skipped keyword '{keyword}': {r.status_code}")
                return []

        soup = BeautifulSoup(r.text, "html.parser")
        listings = soup.select(".job_list_listing") or soup.select("article")

        jobs = []
        for item in listings[:10]:
            title_el = item.select_one("h2 a")
            desc_el = item.select_one("p")
            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue
            desc = desc_el.get_text(strip=True) if desc_el else "—"
            link = f"https://www.skywalker.gr{title_el['href']}" if title_el and title_el.get("href") else None
            posted = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            jobs.append({
                "platform": "Skywalker",
                "title": title,
                "description": desc[:250],
                "budget_amount": "N/A",
                "budget_usd": "N/A",
                "posted": posted,
                "original_url": link,
                "keyword": keyword,
            })
        return jobs
    except Exception as e:
        logger.warning(f"[Skywalker] Error fetching keyword '{keyword}': {e}")
        return []
