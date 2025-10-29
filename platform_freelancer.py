import httpx
import logging
from datetime import datetime, timedelta
from currency_usd import convert_to_usd

logger = logging.getLogger("platform_freelancer")

def fetch_freelancer_jobs():
    logger.info("[Freelancer] Fetching jobs...")
    url = "https://www.freelancer.com/api/projects/0.1/projects/active/?limit=30&sort_field=time_submitted&sort_direction=desc"
    jobs = []
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"[Freelancer] HTTP {r.status_code}")
            return []

        data = r.json().get("result", {}).get("projects", [])
        for job in data:
            title = job.get("title", "N/A")
            desc = job.get("preview_description", "N/A")
            url_job = f"https://www.freelancer.com/projects/{job.get('seo_url', '')}"

            budget = job.get("budget", {})
            amount = budget.get("minimum")
            currency = job.get("currency", {}).get("code", "USD")
            usd = convert_to_usd(amount, currency)

            created_ts = job.get("submitdate", datetime.utcnow().timestamp())
            created_at = datetime.utcfromtimestamp(created_ts)
            if created_at < datetime.utcnow() - timedelta(hours=48):
                continue

            jobs.append({
                "platform": "Freelancer",
                "title": title,
                "description": desc,
                "budget_amount": amount,
                "budget_currency": currency,
                "budget_usd": usd,
                "url": url_job,
                "created_at": created_at.isoformat()
            })
        logger.info(f"[Freelancer] ✅ {len(jobs)} jobs fetched")
        return jobs
    except Exception as e:
        logger.error(f"[Freelancer] Error: {e}")
        return []
