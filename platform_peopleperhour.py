import logging
import httpx
from utils import convert_to_usd

logger = logging.getLogger("PeoplePerHour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"

async def fetch_pph_jobs(keyword):
    """Fetch PPH jobs."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            url = f"{BASE_URL}/search?query={keyword}"
            r = await client.get(url)
            if r.status_code != 200:
                return []
            text = r.text
            jobs = []
            for line in text.split("\n"):
                if "/job/" in line and "title=" in line:
                    title = line.split('title="')[1].split('"')[0]
                    link = "https://www.peopleperhour.com" + line.split('href="')[1].split('"')[0]
                    jobs.append({
                        "id": hash(link),
                        "platform": "peopleperhour",
                        "title": title,
                        "description": "PeoplePerHour job listing",
                        "budget_amount": "N/A",
                        "budget_currency": "GBP",
                        "budget_usd": convert_to_usd(1, "GBP"),
                        "created_at": "now",
                        "affiliate_url": link,
                        "matched_keyword": keyword
                    })
            return jobs[:5]
    except Exception as e:
        logger.error(f"[PPH] Error fetching {keyword}: {e}")
        return []
