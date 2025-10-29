import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger("platform_freelancer")
API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"


def fetch_freelancer_jobs(keywords):
    """Fetch Freelancer.com jobs matching provided keywords"""
    all_jobs = []
    query = ",".join(keywords)
    try:
        params = {
            "full_description": "false",
            "job_details": "false",
            "limit": 30,
            "offset": 0,
            "sort_field": "time_submitted",
            "sort_direction": "desc",
            "query": query,
        }
        with httpx.Client(timeout=15.0) as client:
            r = client.get(API_URL, params=params)
            r.raise_for_status()
            data = r.json()
            for item in data.get("result", {}).get("projects", []):
                title = item.get("title", "").strip()
                desc = (item.get("preview_description") or "").strip()
                budget = item.get("budget", {}) or {}
                budget_min = budget.get("minimum")
                budget_max = budget.get("maximum")
                currency = budget.get("currency", {}).get("code", "USD")
                time_submitted = item.get("time_submitted")
                created_at = (
                    datetime.utcfromtimestamp(time_submitted)
                    if time_submitted
                    else datetime.utcnow()
                )

                # 48-hour filter
                if (datetime.utcnow() - created_at) > timedelta(hours=48):
                    continue

                job = {
                    "title": title,
                    "description": desc,
                    "budget_min": budget_min,
                    "budget_max": budget_max,
                    "budget_currency": currency,
                    "budget_amount": budget_max or budget_min or 0,
                    "created_at": created_at,
                    "platform": "Freelancer",
                    "matched_keyword": _match_keyword(title, desc, keywords),
                    "original_url": f"https://www.freelancer.com/projects/{item.get('seo_url')}",
                }
                all_jobs.append(job)

        logger.info(f"[Freelancer] ✅ {len(all_jobs)} jobs fetched for query: {query}")
    except Exception as e:
        logger.warning(f"[Freelancer] ⚠️ Error: {e}")

    return all_jobs


def _match_keyword(title, desc, keywords):
    text = (title + " " + desc).lower()
    for kw in keywords:
        if kw.lower() in text:
            return kw
    return ""
