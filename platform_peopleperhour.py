import logging
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

logger = logging.getLogger("worker.pph")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"


async def fetch_peopleperhour_jobs():
    """
    Scrapes latest PeoplePerHour jobs (HTML).
    Returns normalized list of dicts.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(BASE_URL)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        job_cards = soup.select("section.job")
        jobs = []

        for card in job_cards:
            title_el = card.select_one("h3.job-title")
            desc_el = card.select_one("p.job-description")
            url_el = card.select_one("a")

            title = title_el.get_text(strip=True) if title_el else "No title"
            desc = desc_el.get_text(strip=True) if desc_el else ""
            url = (
                "https://www.peopleperhour.com"
                + url_el.get("href", "")
                if url_el
                else None
            )

            # Posted date (PPH does not expose exact timestamp; using current time)
            posted_at = datetime.now(timezone.utc)

            jobs.append(
                {
                    "platform": "peopleperhour",
                    "title": title,
                    "description": desc,
                    "budget_amount": None,
                    "budget_currency": None,
                    "posted_at": posted_at,
                    "url": url,
                }
            )

        return jobs

    except Exception as e:
        logger.error(f"PPH fetch error: {e}")
        return []




