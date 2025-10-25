import os
import asyncio
import random
import logging
import httpx
from bs4 import BeautifulSoup
from utils import convert_to_usd
from datetime import datetime, timezone

logger = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

# Rate limiting configuration from .env
PPH_DELAY_MIN = float(os.getenv("PPH_DELAY_MIN", "3"))
PPH_DELAY_MAX = float(os.getenv("PPH_DELAY_MAX", "7"))
PPH_BATCH_LIMIT = int(os.getenv("PPH_BATCH_LIMIT", "2"))

# Global semaphore for concurrent keyword fetches
pph_semaphore = asyncio.Semaphore(PPH_BATCH_LIMIT)


async def fetch_pph_jobs(keyword: str):
    """Fetch jobs from PeoplePerHour safely with delay and concurrency control."""
    await asyncio.sleep(random.uniform(PPH_DELAY_MIN, PPH_DELAY_MAX))  # random delay before each request
    async with pph_semaphore:
        try:
            async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
                response = await client.get(BASE_URL, params={"q": keyword})
                if response.status_code != 200:
                    logger.warning(f"[PPH HTML] Skipped {keyword}: {response.status_code}")
                    return []

            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("section.search-listing > div")
            jobs = []

            for card in cards[:15]:
                title_el = card.select_one("h5 a")
                desc_el = card.select_one("p")
                budget_el = card.select_one(".js-budget")
                time_el = card.select_one(".js-posted")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                description = desc_el.get_text(strip=True) if desc_el else ""
                budget_text = budget_el.get_text(strip=True) if budget_el else ""
                amount = 0
                currency = "USD"

                if "£" in budget_text:
                    currency = "GBP"
                    try:
                        amount = float(budget_text.replace("£", "").split()[0])
                    except Exception:
                        amount = 0
                elif "$" in budget_text:
                    currency = "USD"
                    try:
                        amount = float(budget_text.replace("$", "").split()[0])
                    except Exception:
                        amount = 0
                elif "€" in budget_text:
                    currency = "EUR"
                    try:
                        amount = float(budget_text.replace("€", "").split()[0])
                    except Exception:
                        amount = 0

                usd_value = await convert_to_usd(amount, currency)
                posted = time_el.get_text(strip=True) if time_el else "recently"

                jobs.append({
                    "platform": "PeoplePerHour",
                    "title": title,
                    "description": description[:250],
                    "budget_amount": f"{amount:.1f} {currency}",
                    "budget_usd": f"~${usd_value:.1f} USD",
                    "posted": posted,
                    "original_url": title_el["href"],
                    "keyword": keyword,
                })

            logger.info(f"[PPH HTML] ✅ Retrieved {len(jobs)} jobs for keyword '{keyword}'")
            return jobs

        except httpx.RequestError as e:
            logger.warning(f"[PPH HTML] Network error for '{keyword}': {e}")
            return []
        except Exception as e:
            logger.warning(f"[PPH HTML] Error fetching keyword '{keyword}': {e}")
            return []
