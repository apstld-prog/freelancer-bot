import logging, httpx, hashlib, xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any

log = logging.getLogger("skywalker")

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

async def fetch_skywalker_jobs() -> List[Dict[str, Any]]:
    url = "https://www.skywalker.gr/jobs/feed"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        if r.status_code != 200:
            log.warning(f"Skywalker status {r.status_code}")
            return []
        xml_text = r.text
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")
        jobs = []
        for it in items:
            title = it.findtext("title", "")
            link = it.findtext("link", "")
            desc = it.findtext("description", "")
            job_hash = hashlib.sha1(f"{title}{desc}".encode()).hexdigest()
            jobs.append({
                "title": title, "url": link, "description": desc,
                "budget_text": "—", "source": "Skywalker",
                "job_hash": job_hash, "created_at": datetime.utcnow(),
            })
        log.info(f"Skywalker parsed {len(jobs)} entries")
        return jobs
