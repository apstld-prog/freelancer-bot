import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger("platform_freelancer")


async def fetch_freelancer_jobs(keyword):
    """Fetch latest jobs from Freelancer API by keyword with proper budget + USD conversion."""
    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/active/"
        "?full_description=false&job_details=false&limit=30&sort_field=time_submitted"
        "&sort_direction=desc&query=" + keyword
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"[Freelancer error for '{keyword}']: {e}")
        return []

    jobs = []
    projects = data.get("result", {}).get("projects", [])
    for project in projects:
        try:
            title = project.get("title", "Untitled")
            desc = project.get("preview_description", "")
            currency = project.get("currency", {}).get("code", "N/A")
            budget = project.get("budget", {})
            min_budget = budget.get("minimum", 0)
            max_budget = budget.get("maximum", 0)

            # USD conversion approximations
            conversion_rates = {"USD": 1.0, "EUR": 1.08, "GBP": 1.28, "AUD": 0.66, "CAD": 0.73}
            rate = conversion_rates.get(currency, 1.0)

            if min_budget and max_budget:
                avg_budget = (min_budget + max_budget) / 2
            elif min_budget or max_budget:
                avg_budget = min_budget or max_budget
            else:
                avg_budget = None

            usd_amount = None
            if avg_budget:
                usd_amount = round(avg_budget * rate, 2)

            # Build formatted budget display
            if avg_budget:
                if usd_amount and currency != "USD":
                    budget_display = f"{min_budget}–{max_budget} {currency} (~${usd_amount} USD)"
                else:
                    budget_display = f"{min_budget}–{max_budget} {currency}"
            else:
                budget_display = "N/A"

            # Time posted
            posted_ts = project.get("submitdate")
            if posted_ts:
                dt = datetime.fromtimestamp(posted_ts, tz=timezone.utc)
                posted = dt.strftime("%Y-%m-%d %H:%M UTC")
            else:
                posted = "unknown"

            jobs.append(
                {
                    "platform": "Freelancer",
                    "title": title,
                    "description": desc.strip(),
                    "budget_display": budget_display,
                    "budget_amount": avg_budget,
                    "budget_currency": currency,
                    "budget_usd": usd_amount,
                    "keyword": keyword,
                    "url": f"https://www.freelancer.com/projects/{project.get('seo_url', '')}",
                    "posted_at": posted,
                }
            )
        except Exception as e:
            logger.warning(f"[Freelancer parse error]: {e}")

    logger.info(f"[Freelancer] total merged: {len(jobs)}")
    return jobs
