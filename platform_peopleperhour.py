import logging, httpx, hashlib
from datetime import datetime
from typing import List, Dict, Any

log = logging.getLogger("platform_peopleperhour")

RATES = {"USD": 1.0, "EUR": 1.07, "GBP": 1.23, "AUD": 0.65, "CAD": 0.72, "INR": 0.012, "PHP": 0.017, "BRL": 0.18}

def format_budget(min_budget, max_budget, currency):
    if not min_budget:
        return "Budget: —"
    if currency not in RATES:
        RATES[currency] = 1.0
    usd_min = float(min_budget) * RATES[currency]
    usd_max = float(max_budget) * RATES[currency] if max_budget else None

    if currency == "USD":
        if max_budget:
            return f"Budget: ${min_budget:,.2f}–${max_budget:,.2f} USD"
        return f"Budget: ${min_budget:,.2f} USD"
    else:
        if max_budget:
            return f"Budget: {min_budget:,.2f}–{max_budget:,.2f} {currency} (~${usd_min:,.2f}–${usd_max:,.2f} USD)"
        return f"Budget: {min_budget:,.2f} {currency} (~${usd_min:,.2f} USD)"

async def fetch_peopleperhour_jobs(keyword: str) -> List[Dict[str, Any]]:
    results = []
    url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
    proxy = f"https://pph-proxy-service.onrender.com/api/pph?key=1211&q={keyword}"
    async with httpx.AsyncClient(timeout=25) as client:
        try:
            r = await client.get(proxy)
            if r.status_code == 200:
                data = r.json()
                for j in data.get("jobs", []):
                    title = j.get("title")
                    link = j.get("url") or url
                    desc = j.get("desc", "")
                    budget_min = j.get("min", 0)
                    budget_max = j.get("max", 0)
                    currency = j.get("currency", "USD")
                    btxt = format_budget(budget_min, budget_max, currency)
                    job_hash = hashlib.sha1(f"{title}{desc}".encode()).hexdigest()
                    results.append({
                        "title": title, "url": link, "description": desc, "budget_text": btxt,
                        "source": "PeoplePerHour", "job_hash": job_hash,
                        "created_at": datetime.utcnow(),
                    })
        except Exception as e:
            log.error(f"[PPH] fetch error: {e}")
    log.info(f"[PPH total merged: {len(results)}]")
    return results
