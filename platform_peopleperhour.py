import logging
import httpx
from utils import convert_to_usd

logger = logging.getLogger("PeoplePerHour")

BASE_URL = "https://www.peopleperhour.com"

async def fetch_pph_jobs(keyword):
    """Fetch PeoplePerHour jobs by keyword in title or description."""
    try:
        search_url = f"{BASE_URL}/freelance-{keyword}-jobs"
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(search_url)
            if r.status_code != 200:
                logger.warning(f"[PPH] HTTP {r.status_code} for {keyword}")
                return []

            text = r.text
            lines = text.split("\n")
            jobs = []
            for line in lines:
                if '/job/' in line and 'title="' in line:
                    title = line.split('title="')[1].split('"')[0]
                    if keyword.lower() not in title.lower():
                        continue
                    href = line.split('href="')[1].split('"')[0]
                    link = BASE_URL + href
                    jobs.append({
                        "id": hash(link),
                        "platform": "peopleperhour",
                        "title": title.strip(),
                        "description": f"Job related to '{keyword}' on PeoplePerHour.",
                        "budget_amount": "N/A",
                        "budget_currency": "GBP",
                        "budget_usd": convert_to_usd(1, "GBP"),
                        "created_at": "now",
                        "affiliate_url": link,
                        "keyword": keyword
                    })
            return jobs[:10]
    except Exception as e:
        logger.error(f"[PPH] Error fetching {keyword}: {e}")
        return []
