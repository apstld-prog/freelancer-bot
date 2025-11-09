import logging
import httpx
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger("platform.careerjet")

BASE_URL = "https://www.careerjet.com/search/jobs?s={query}"


def parse_relative_date(text: str) -> datetime:
    """Converts '2 days ago', '5 hours ago' → datetime."""
    text = text.lower().strip()

    now = datetime.now(tz=timezone.utc)

    try:
        if "hour" in text:
            num = int(text.split()[0])
            return now - timedelta(hours=num)

        if "day" in text:
            num = int(text.split()[0])
            return now - timedelta(days=num)

        if "minute" in text:
            num = int(text.split()[0])
            return now - timedelta(minutes=num)

        # Unknown → fallback
        return now

    except:
        return now


async def fetch_careerjet_jobs(keywords: list[str]):
    """
    Scrapes CareerJet.

    Normalized output structure:
    {
        "platform": "careerjet",
        "title": str,
        "description": str,
        "budget_amount": None,
        "budget_currency": None,
        "posted_at": datetime,
        "url": str
    }
    """

    query = "+".join(keywords) if keywords else ""
    url = BASE_URL.format(query=query)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        jobs = []

        for card in soup.select(".job"):
            a = card.select_one("a.title")
            if not a:
                continue

            job_url = a.get("href")
            if not job_url:
                continue

            if job_url.startswith("/"):
                job_url = "https://www.careerjet.com" + job_url

            title = a.get_text(strip=True)

            desc_el = card.select_one(".desc")
            description = desc_el.get_text(strip=True) if desc_el else ""

            date_el = card.select_one(".date")
            if date_el:
                posted_at = parse_relative_date(date_el.get_text(strip=True))
            else:
                posted_at = datetime.now(tz=timezone.utc)

            jobs.append(
                {
                    "platform": "careerjet",
                    "title": title,
                    "description": description,
                    "budget_amount": None,
                    "budget_currency": None,
                    "posted_at": posted_at,
                    "url": job_url,
                }
            )

        return jobs

    except Exception as e:
        logger.error(f"CareerJet error: {e}")
        return []


