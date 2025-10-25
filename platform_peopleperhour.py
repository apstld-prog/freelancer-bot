import httpx
import asyncio
import random
from datetime import datetime
from utils import convert_to_usd

PPH_SEARCH_URL = "https://www.peopleperhour.com/freelance-jobs?q="

async def fetch_pph_jobs(keyword):
    jobs = []
    try:
        await asyncio.sleep(random.uniform(3.0, 5.5))
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(f"{PPH_SEARCH_URL}{keyword}")
            if resp.status_code != 200 or "Too Many Requests" in resp.text:
                print(f"[PPH] Error fetching '{keyword}': {resp.status_code}")
                return []

            for line in resp.text.splitlines():
                if "job-title-link" in line:
                    title = line.strip().split(">")[1].split("<")[0]
                    url = "https://www.peopleperhour.com" + line.split('href="')[1].split('"')[0]
                    budget_display = "Budget: N/A"

                    if "£" in line:
                        amount = line.split("£")[1].split("<")[0].strip()
                        try:
                            val = float(amount.replace(",", ""))
                            usd_val = convert_to_usd(val, "GBP")
                            if usd_val:
                                budget_display = f"£{val} (~${usd_val} USD)"
                        except:
                            pass

                    jobs.append({
                        "platform": "PeoplePerHour",
                        "title": title,
                        "description": "Job description unavailable.",
                        "affiliate_url": url,
                        "budget_display": budget_display,
                        "matched_keyword": keyword,
                        "created_at": datetime.utcnow().isoformat()
                    })
    except Exception as e:
        print(f"[PPH] Error fetching keyword '{keyword}': {e}")
    return jobs
