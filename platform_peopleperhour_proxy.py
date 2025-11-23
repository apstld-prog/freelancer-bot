# FINAL PeoplePerHour API Scraper via Proxy
import httpx
from typing import List, Dict, Optional
from config import PEOPLEPERHOUR_PROXY_URL

API_URL = "https://www.peopleperhour.com/api/search/freelance-jobs"

def _proxy_fetch_json(url: str, timeout: float = 15.0) -> Optional[dict]:
    """
    Fetch JSON through Render PPH Proxy using /fetch endpoint.
    """
    try:
        r = httpx.get(f"{PEOPLEPERHOUR_PROXY_URL}", params={"url": url}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None

def get_items(keywords: List[str]) -> List[Dict]:
    out = []

    for kw in keywords:
        # Build API query URL
        url = f"{API_URL}?search={kw}&page=1"

        data = _proxy_fetch_json(url)
        if not data:
            continue

        # The jobs live inside data["results"]
        jobs = data.get("results", [])
        for job in jobs:
            title = job.get("title", "")
            if not title:
                continue

            # SEO URL structure for job link
            job_id = job.get("id")
            seo_url = job.get("seo_url", "")
            full_url = f"https://www.peopleperhour.com/freelance-jobs/{seo_url}-{job_id}"

            budget = job.get("budget", {}) or {}
            bmin = budget.get("minimum")
            bmax = budget.get("maximum")
            cur = budget.get("currency", "USD")

            out.append({
                "source": "peopleperhour",
                "matched_keyword": kw,
                "title": title,
                "original_url": full_url,
                "proposal_url": full_url,
                "description": job.get("description", ""),
                "description_html": job.get("description", ""),
                "budget_min": bmin,
                "budget_max": bmax,
                "currency": cur,
                "time_submitted": job.get("publish_date"),
            })

    return out
