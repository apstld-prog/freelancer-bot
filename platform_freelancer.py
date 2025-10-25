import logging
import httpx
from datetime import datetime, timezone
from utils import convert_to_usd

logger = logging.getLogger("platform_freelancer")

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

async def fetch_freelancer_jobs(keyword: str):
    try:
        params = {
            "full_description": False,
            "job_details": False,
            "limit": 30,
            "offset": 0,
            "sort_field": "time_submitted",
            "sort_direction": "desc",
            "query": keyword,
        }

        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            r = await client.get(API_URL, params=params)
            r.raise_for_status()
            data = r.json()

        jobs = []
        for p in data.get("result", {}).get("projects", []):
            title = p.get("title", "N/A")
            description = p.get("preview_description", "—")
            budget = p.get("budget", {})
            min_b = budget.get("minimum") or 0
            max_b = budget.get("maximum") or 0
            currency = budget.get("currency", {}).get("code", "USD")

            usd_value = convert_to_usd(max_b or min_b, currency)
            created = datetime.fromtimestamp(p.get("submitdate", 0), tz=timezone.utc)
            age_minutes = int((datetime.now(timezone.utc) - created).total_seconds() / 60)
            posted = f"{age_minutes} min ago" if age_minutes < 60 else f"{age_minutes // 60} h ago"

            jobs.append({
                "platform": "Freelancer",
                "title": title,
                "description": description[:250],
                "budget_amount": f"{min_b}–{max_b} {currency}" if max_b else f"{min_b} {currency}",
                "budget_usd": f"~${usd_value} USD",
                "posted": posted,
                "original_url": f"https://www.freelancer.com/projects/{p.get('seo_url', '')}",
                "keyword": keyword,
            })
        return jobs
    except Exception as e:
        logger.warning(f"[Freelancer] Error fetching {keyword}: {e}")
        return []
