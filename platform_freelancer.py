# ======================================================
# platform_freelancer.py — Fetch active jobs from Freelancer.com
# ======================================================
import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("platform_freelancer")

BASE_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
SEARCH_URL = "https://www.freelancer.com/api/projects/0.1/projects/search/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (FreelancerFeedBot)",
    "Accept": "application/json"
}

def _fetch_from_endpoint(client, url, params):
    try:
        r = client.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            logger.warning(f"[Freelancer] HTTP {r.status_code} for {url}")
            return []
        data = r.json().get("result", {}).get("projects", [])
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"[Freelancer] fetch error: {e}")
        return []

def fetch_freelancer_jobs(keywords):
    """Fetch and normalize Freelancer.com projects per keywords."""
    all_jobs = []
    if not keywords:
        return []

    with httpx.Client() as client:
        for kw in keywords:
            params_main = {
                "limit": 30,
                "offset": 0,
                "sort_field": "time_submitted",
                "sort_direction": "desc",
                "query": kw
            }
            jobs = _fetch_from_endpoint(client, BASE_URL, params_main)
            if not jobs:
                # fallback to search/projects
                params_search = {"query": kw, "or_terms": kw, "limit": 30}
                jobs = _fetch_from_endpoint(client, SEARCH_URL, params_search)
            for j in jobs:
                try:
                    title = j.get("title", "").strip()
                    desc = j.get("preview_description", "").strip()
                    budget = j.get("budget", {}) or {}
                    budget_amount = f"{budget.get('minimum', 'N/A')} - {budget.get('maximum', 'N/A')}"
                    currency = budget.get("currency", {}).get("code", "USD")
                    created_ts = j.get("submitdate") or j.get("time_submitted")
                    created = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else None

                    all_jobs.append({
                        "platform": "Freelancer",
                        "title": title,
                        "description": desc,
                        "budget": budget_amount,
                        "currency": currency,
                        "created_at": created.isoformat() if created else None,
                        "url": f"https://www.freelancer.com/projects/{j.get('seo_url', '')}",
                        "keyword": kw
                    })
                except Exception as e:
                    logger.warning(f"[Freelancer] job parse error: {e}")
    return all_jobs
