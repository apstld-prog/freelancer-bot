import httpx
import logging
from datetime import datetime, timezone
from utils import convert_to_usd, format_time_ago

logger = logging.getLogger("freelancer")

async def fetch_freelancer_jobs(keyword):
    """Fetch and format job results from Freelancer.com API."""
    try:
        url = (
            "https://www.freelancer.com/api/projects/0.1/projects/active/"
            f"?query={keyword}&limit=30&full_description=true"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            raw = response.json()
    except Exception as e:
        logger.error(f"[Freelancer] Error fetching for '{keyword}': {e}")
        return []

    projects = raw.get("result", {}).get("projects", [])
    jobs = []

    for proj in projects:
        try:
            title = proj.get("title", "Untitled")
            desc = proj.get("preview_description", "") or ""
            budget = proj.get("budget", {}) or {}
            amount = budget.get("minimum", 0)
            currency = (budget.get("currency", {}) or {}).get("code", "USD")

            usd_value = convert_to_usd(amount, currency)

            created_at = proj.get("submitdate") or proj.get("time_submitted")
            posted = format_time_ago(created_at) if created_at else "N/A"
            url = f"https://www.freelancer.com/projects/{proj.get('seo_url','')}/{proj.get('id','')}"

            formatted = (
                f"<b>🧭 Platform:</b> Freelancer\n"
                f"<b>📄 Title:</b> {title}\n"
                f"<b>🔑 Keyword:</b> {keyword}\n"
                f"<b>💰 Budget:</b> {currency} {amount} (~${usd_value} USD)\n"
                f"<b>🕓 Posted:</b> {posted}\n\n"
                f"{desc.strip()}\n\n"
                f"<a href='{url}'>🔗 View Project</a>"
            )

            jobs.append({
                "platform": "Freelancer",
                "title": title,
                "description": desc,
                "keyword": keyword,
                "budget_amount": amount,
                "budget_currency": currency,
                "budget_usd": usd_value,
                "created_at": created_at,
                "url": url,
                "formatted": formatted,
            })
        except Exception as e:
            logger.warning(f"[Freelancer] Skipped job due to error: {e}")

    logger.info(f"[Freelancer] Retrieved {len(jobs)} jobs for keyword '{keyword}'")
    return jobs
