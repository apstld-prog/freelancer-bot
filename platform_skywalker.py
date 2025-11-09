import logging
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

logger = logging.getLogger("worker.skywalker")

BASE_URL = "https://www.skywalker.gr/el/el/jobs/search?keywords={query}"


async def fetch_skywalker_jobs(keywords: list[str]):
    """
    Scrape Skywalker job listings.
    Normalized output:
    {
        "platform": "skywalker",
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

        for item in soup.select("article.article-item"):

            # URL
            link = item.select_one("a")
            if not link:
                continue

            href = link.get("href")
            if not href:
                continue

            if href.startswith("http"):
                url = href
            else:
                url = "https://www.skywalker.gr" + href

            # Title
            title_el = item.select_one(".article-title")
            title = title_el.get_text(strip=True) if title_el else "Job"

            # Description
            desc_el = item.select_one(".article-desc")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Skywalker rarely shows post date — fallback to NOW
            posted_at = datetime.now(tz=timezone.utc)

            # No budget info
            budget_amount = None
            budget_currency = None

            jobs.append(
                {
                    "platform": "skywalker",
                    "title": title,
                    "description": description,
                    "budget_amount": budget_amount,
                    "budget_currency": budget_currency,
                    "posted_at": posted_at,
                    "url": url,
                }
            )

        return jobs

    except Exception as e:
        logger.error(f"Skywalker fetch error: {e}")
        return []


