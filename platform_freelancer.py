import httpx, logging
from datetime import datetime, timezone
from utils_fx import convert_to_usd

log = logging.getLogger("worker.freelancer")
BASE = "https://www.freelancer.com/api/projects/0.1/projects/active/?full_description=false&job_details=false&limit=25&offset=0&sort_field=time_submitted&sort_direction=desc"

def fetch_freelancer_jobs():
    """Return parsed job objects."""
    jobs = []
    try:
        r = httpx.get(BASE, timeout=20)
        data = r.json()
        for p in data.get("result", {}).get("projects", []):
            jobs.append({
                "platform": "Freelancer",
                "title": p.get("title", "Untitled"),
                "description": p.get("preview_description", ""),
                "original_url": f"https://www.freelancer.com/projects/{p.get('seo_url')}",
                "budget_amount": p.get("budget", {}).get("minimum", 0),
                "budget_currency": p.get("currency", {}).get("code", "USD"),
                "budget_usd": convert_to_usd(p.get("budget", {}).get("minimum", 0),
                                              p.get("currency", {}).get("code", "USD")),
                "created_at": datetime.fromtimestamp(p.get("submitdate", 0), tz=timezone.utc)
            })
    except Exception as e:
        log.error(f"Fetch error: {e}")
    return jobs


