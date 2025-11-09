import logging
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

logger = logging.getLogger("platform.kariera")

BASE_URL = "https://www.kariera.gr/el/jobs?keywords={query}"


async def fetch_kariera_jobs(keywords: list[str]):
    """
    Scrapes Kariera.gr job listings.

    Normalized output:
    {
        "platform": "kariera",
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
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        jobs = []

        for el in soup.select("article"):
            a = el.select_one("a")
            if not a:
                continue

            job_url = a.get("href")
            if not job_url:
                continue

            if job_url.startswith("/"):
                job_url = "https://www.kariera.gr" + job_url

            title = a.get_text(strip=True)

            # Description snippet
            desc_el = el.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Kariera also rarely gives clean date → fallback now
            posted_at = datetime.now(tz=timezone.utc)

            jobs.append(
                {
                    "platform": "kariera",
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
        logger.error(f"Kariera fetch error: {e}")
        return []



