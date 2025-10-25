import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import asyncio
from utils import convert_to_usd

logger = logging.getLogger("platform_pph")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

REQUEST_DELAY = 5  # seconds delay to avoid PPH rate-limit (429)


async def fetch_pph_jobs(keyword: str):
    try:
        await asyncio.sleep(REQUEST_DELAY)

        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            r = await client.get(BASE_URL, params={"q": keyword})
            if r.status_code == 429:
                logger.warning(f"[PPH HTML] Rate-limited for '{keyword}', skipping...")
                return []
            if r.status_code != 200:
                logger.warning(f"[PPH HTML] Error fetching '{keyword}': {r.status_code}")
                return []

        soup = BeautifulSoup(r.text, "html.parser")
        listings = soup.select(".JobSearchCard-item") or []
        jobs = []

        for item in listings[:10]:
            title_el = item.select_one(".JobSearchCard-primary-heading a")
            desc_el = item.select_one(".JobSearchCard-primary-description")
            budget_el = item.select_one(".JobSearchCard-secondary-price")

            title = title_el.get_text(strip=True) if title_el else "N/A"
            desc = desc_el.get_text(strip=True) if desc_el else "—"
            link = f"https://www.peopleperhour.com{title_el['href']}" if title_el and title_el.get("href") else None
            budget_raw = budget_el.get_text(strip=True) if budget_el else "N/A"

            currency = "GBP" if "£" in budget_raw else "EUR" if "€" in budget_raw else "USD"
            try:
                amount = float("".join(ch for ch in budget_raw if ch.isdigit() or ch == "."))
            except:
                amount = 0.0

            usd_value = convert_to_usd(amount, currency)
            posted = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            jobs.append({
                "platform": "PeoplePerHour",
                "title": title,
                "description": desc[:250],
                "budget_amount": f"{budget_raw}",
                "budget_usd": f"~${usd_value} USD",
                "posted": posted,
                "original_url": link,
                "keyword": keyword,
            })
        return jobs
    except Exception as e:
        logger.warning(f"[PPH HTML] Error fetching keyword '{keyword}': {e}")
        return []
