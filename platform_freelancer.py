import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("worker.freelancer")

API_URL = (
    "https://www.freelancer.com/api/projects/0.1/projects/active/"
    "?full_description=true&job_details=true&limit=50&sort_field=time_submitted"
    "&sort_direction=desc&query={query}"
)


async def fetch_freelancer_jobs(keywords: list[str]):
    """
    Fetch jobs from Freelancer.com API.

    Returns normalized job list:
    [
        {
            "platform": "freelancer",
            "title": str,
            "description": str,
            "budget_amount": int|None,
            "budget_currency": str|None,
            "posted_at": datetime,
            "url": str
        }
    ]
    """
    try:
        query = ",".join(keywords) if keywords else ""
        url = API_URL.format(query=query)

        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        jobs = []
        for p in data.get("result", {}).get("projects", []):
            title = p.get("title", "")
            desc = p.get("preview_description", "")

            budget_amount = None
            budget_currency = None

            if "budget" in p and p["budget"]:
                budget_amount = p["budget"].get("minimum")
                budget_currency = p["currency"]["code"] if p.get("currency") else None

            posted_at = datetime.fromtimestamp(
                p.get("time_submitted", 0),
                tz=timezone.utc
            )

            url = f"https://www.freelancer.com/projects/{p.get('seo_url', '')}"

            jobs.append(
                {
                    "platform": "freelancer",
                    "title": title,
                    "description": desc,
                    "budget_amount": budget_amount,
                    "budget_currency": budget_currency,
                    "posted_at": posted_at,
                    "url": url,
                }
            )

        return jobs

    except Exception as e:
        logger.error(f"Freelancer fetch error: {e}")
        return []

