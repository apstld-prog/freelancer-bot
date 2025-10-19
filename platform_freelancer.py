import httpx
from datetime import datetime

def fetch(keywords=None, fresh_since=None, limit=50, logger=None):
    url = "https://www.freelancer.com/api/projects/0.1/projects/active/?full_description=false&job_details=false&limit=30&offset=0&sort_field=time_submitted&sort_direction=desc"
    if keywords:
        query = ",".join(keywords) if isinstance(keywords, list) else keywords
        url += f"&query={query}"
    if logger:
        logger.info(f"[Freelancer] Fetching from {url}")
    try:
        r = httpx.get(url, timeout=15)
        data = r.json().get("result", {}).get("projects", [])
        results = []
        for j in data:
            budget = j.get("budget", {})
            results.append({
                "platform": "freelancer",
                "title": j.get("title"),
                "description": j.get("preview_description"),
                "affiliate_url": f"https://www.freelancer.com/projects/{j.get('seo_url', '')}",
                "original_url": f"https://www.freelancer.com/projects/{j.get('seo_url', '')}",
                "budget_amount": budget.get("minimum"),
                "budget_currency": budget.get("currency", {}).get("code"),
                "budget_usd": budget.get("minimum_usd"),
                "created_at": datetime.utcfromtimestamp(j.get("time_submitted", 0)).isoformat()
            })
            if len(results) >= limit:
                break
        if logger:
            logger.info(f"[Freelancer] fetched={len(results)}")
        return results
    except Exception as e:
        if logger:
            logger.error(f"[Freelancer] error: {e}")
        return []

# Wrapper to match worker_runner expectations
def get_items(keywords=None, fresh_since=None, limit=50, logger=None):
    return fetch(keywords=keywords, fresh_since=fresh_since, limit=limit, logger=logger)
