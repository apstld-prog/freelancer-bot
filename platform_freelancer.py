import httpx
from utils import convert_to_usd
from datetime import datetime

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

async def fetch_freelancer_jobs(keyword):
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            params = {
                "query": keyword,
                "limit": 20,
                "full_description": "true",
                "sort_field": "time_submitted",
                "sort_direction": "desc"
            }
            resp = await client.get(API_URL, params=params)
            data = resp.json().get("result", {}).get("projects", [])
            for item in data:
                title = item.get("title", "")
                desc = item.get("preview_description", "")
                currency = item.get("currency", {}).get("code", "USD")
                budget_min = item.get("budget", {}).get("minimum")
                budget_max = item.get("budget", {}).get("maximum")

                if budget_min and budget_max:
                    budget_display = f"{budget_min}–{budget_max} {currency}"
                    if currency != "USD":
                        usd_min = convert_to_usd(budget_min, currency)
                        usd_max = convert_to_usd(budget_max, currency)
                        if usd_min and usd_max:
                            budget_display += f" (~${usd_min}–${usd_max} USD)"
                else:
                    budget_display = "Budget: N/A"

                jobs.append({
                    "platform": "Freelancer",
                    "title": title,
                    "description": desc,
                    "affiliate_url": f"https://www.freelancer.com/projects/{item.get('seo_url')}",
                    "budget_display": budget_display,
                    "matched_keyword": keyword,
                    "created_at": datetime.utcnow().isoformat()
                })
    except Exception as e:
        print(f"[Freelancer] Error fetching {keyword}: {e}")
    return jobs
