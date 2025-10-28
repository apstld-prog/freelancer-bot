import logging
import httpx
from datetime import datetime, timedelta

def fetch_freelancer_jobs():
    """Fetch and filter jobs from Freelancer API"""
    try:
        url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
        params = {
            "limit": 30,
            "offset": 0,
            "full_description": True,
            "sort_field": "time_submitted",
            "sort_direction": "desc"
        }
        jobs = []
        with httpx.Client(timeout=25) as client:
            r = client.get(url, params=params)
            if r.status_code != 200:
                logging.warning(f"[Freelancer] HTTP {r.status_code}")
                return []
            for j in r.json().get("result", {}).get("projects", []):
                created_at = datetime.utcfromtimestamp(j.get("time_submitted", 0))
                if datetime.utcnow() - created_at > timedelta(hours=48):
                    continue
                jobs.append({
                    "id": j.get("id"),
                    "title": j.get("title"),
                    "description": j.get("preview_description", ""),
                    "budget_amount": j.get("budget", {}).get("minimum", 0),
                    "budget_currency": j.get("currency", {}).get("code", "USD"),
                    "original_url": f"https://www.freelancer.com/projects/{j.get('seo_url')}",
                    "platform": "Freelancer",
                    "created_at": created_at
                })
        logging.info(f"[Freelancer] ✅ Collected {len(jobs)} recent jobs")
        return jobs
    except Exception as e:
        logging.error(f"[Freelancer] Exception: {e}")
        return []
