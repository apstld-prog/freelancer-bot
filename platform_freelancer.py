import logging
import httpx
from datetime import datetime, timezone, timedelta
from currency_usd import usd_line

logger = logging.getLogger("platform_freelancer")

API_URL = (
    "https://www.freelancer.com/api/projects/0.1/projects/active/"
    "?limit=30&sort_field=time_submitted&sort_direction=desc&full_description=false"
)


def _parse_posted_ago(seconds_ago: int) -> str:
    if seconds_ago < 60:
        return f"{seconds_ago} seconds ago"
    minutes = seconds_ago // 60
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago"
    days = hours // 24
    return f"{days} days ago"


def fetch_freelancer_jobs(keywords: list[str]) -> list[dict]:
    try:
        logger.info("[Freelancer] Fetching jobs...")
        query = ",".join(keywords) if keywords else ""
        url = f"{API_URL}&query={query}"

        with httpx.Client(timeout=30.0) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()

        projects = data.get("result", {}).get("projects", [])
        logger.info(f"[Freelancer] ✅ {len(projects)} jobs fetched")

        jobs = []
        for p in projects:
            title = p.get("title", "No title")
            desc = p.get("preview_description", "")
            currency = p.get("currency", {}).get("code", "USD")
            min_amt = p.get("budget", {}).get("minimum")
            max_amt = p.get("budget", {}).get("maximum")
            time_submitted = p.get("time_submitted")

            posted_ago = None
            if time_submitted:
                dt = datetime.fromtimestamp(time_submitted, tz=timezone.utc)
                delta = datetime.now(timezone.utc) - dt
                posted_ago = _parse_posted_ago(int(delta.total_seconds()))

            usd_info = usd_line(min_amt, max_amt, currency)

            matched_kw = None
            if keywords:
                text = f"{title} {desc}".lower()
                for kw in keywords:
                    if kw.lower() in text:
                        matched_kw = kw
                        break

            jobs.append({
                "platform": "Freelancer",
                "title": title.strip(),
                "description": desc.strip(),
                "budget": usd_info,
                "currency": currency,
                "min_amount": min_amt,
                "max_amount": max_amt,
                "created_at": datetime.fromtimestamp(time_submitted, tz=timezone.utc)
                if time_submitted else None,
                "posted_ago": posted_ago,
                "url": f"https://www.freelancer.com/projects/{p.get('seo_url', '')}",
                "keyword": matched_kw or "N/A",
            })
        return jobs

    except Exception as e:
        logger.error(f"[Freelancer] Error: {e}")
        return []
