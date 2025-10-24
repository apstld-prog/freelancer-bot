import logging, httpx, hashlib
from datetime import datetime
from typing import List, Dict, Any

log = logging.getLogger("platform_freelancer")

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

def parse_freelancer_jobs(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    projects = []
    for proj in raw.get("result", {}).get("projects", []):
        title = proj.get("title")
        url = f"https://www.freelancer.com/projects/{proj.get('seo_url', '')}"
        desc = proj.get("preview_description", "")
        budget = proj.get("budget", {})
        min_b = budget.get("minimum", 0)
        max_b = budget.get("maximum", 0)
        curr = budget.get("currency", {}).get("code", "USD")
        btxt = format_budget(min_b, max_b, curr)
        job_hash = hashlib.sha1(f"{title}{desc}".encode()).hexdigest()
        projects.append({
            "title": title, "url": url, "description": desc, "budget_text": btxt,
            "source": "Freelancer", "job_hash": job_hash,
            "created_at": datetime.utcnow(),
        })
    log.info(f"[Freelancer] total merged: {len(projects)}")
    return projects

async def fetch_freelancer_jobs(keyword: str) -> List[Dict[str, Any]]:
    url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?full_description=false&job_details=false&limit=30&sort_field=time_submitted&sort_direction=desc&query={keyword}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        if r.status_code != 200:
            log.warning(f"[Freelancer] status {r.status_code} for '{keyword}'")
            return []
        data = r.json()
        return parse_freelancer_jobs(data)
