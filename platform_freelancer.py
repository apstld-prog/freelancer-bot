import logging
import httpx
from utils import convert_to_usd

logger = logging.getLogger("Freelancer")

BASE_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

async def fetch_freelancer_jobs(keyword):
    """Fetch Freelancer.com projects filtered by keyword in title or description."""
    try:
        params = {
            "query": keyword,
            "limit": 20,
            "offset": 0,
            "full_description": True,
            "job_details": True,
            "sort_field": "time_submitted",
            "sort_direction": "desc"
        }
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(BASE_URL, params=params)
            r.raise_for_status()
            data = r.json()
            projects = data.get("result", {}).get("projects", [])
            jobs = []
            for p in projects:
                title = p.get("title", "")
                desc = p.get("preview_description", "")
                # ✅ Filter only if keyword appears in title or description
                if keyword.lower() not in title.lower() and keyword.lower() not in desc.lower():
                    continue

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
                    "title": title,
                    "description": desc,
                    "budget_amount": budget_str,
                    "budget_currency": currency,
                    "budget_usd": converted,
                    "created_at": p.get("time_submitted", ""),
                    "affiliate_url": f"https://www.freelancer.com/projects/{p['seo_url']}",
                    "keyword": keyword
                })

            return jobs[:10]
    except Exception as e:
        logger.error(f"[Freelancer] Error fetching {keyword}: {e}")
        return []
