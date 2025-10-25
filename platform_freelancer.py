import logging
import httpx
from utils import convert_to_usd

logger = logging.getLogger("Freelancer")

BASE_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

async def fetch_freelancer_jobs(keyword):
    """Fetch Freelancer.com projects for a keyword."""
    try:
        params = {
            "query": keyword,
            "limit": 5,
            "offset": 0,
            "full_description": False,
            "job_details": False,
            "sort_field": "time_submitted",
            "sort_direction": "desc"
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(BASE_URL, params=params)
            r.raise_for_status()
            data = r.json()
            projects = data.get("result", {}).get("projects", [])
            jobs = []
            for p in projects:
                budget = p.get("budget", {})
                min_b, max_b = budget.get("minimum"), budget.get("maximum")
                currency = budget.get("currency", {}).get("code", "USD")
                if max_b or min_b:
                    budget_str = f"{min_b or ''}-{max_b or ''}".strip("-")
                else:
                    budget_str = "N/A"
                converted = convert_to_usd(max_b or min_b, currency)
                jobs.append({
                    "id": p["id"],
                    "platform": "freelancer",
                    "title": p.get("title", "Untitled"),
                    "description": p.get("preview_description", ""),
                    "budget_amount": budget_str,
                    "budget_currency": currency,
                    "budget_usd": converted,
                    "created_at": p.get("time_submitted", ""),
                    "affiliate_url": f"https://www.freelancer.com/projects/{p['seo_url']}",
                    "matched_keyword": keyword
                })
            return jobs
    except Exception as e:
        logger.error(f"[Freelancer] Error fetching {keyword}: {e}")
        return []
