import httpx, logging
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from utils_fx import convert_to_usd

log = logging.getLogger("worker.skywalker")
URL = "https://www.skywalker.gr/el/theseis-ergasias"

def fetch_skywalker_jobs():
    jobs = []
    try:
        r = httpx.get(URL, timeout=20, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")
        for c in soup.select("div.job-item"):
            title_el = c.select_one("a.job-title")
            desc_el = c.select_one("div.job-desc")
            title = title_el.get_text(strip=True) if title_el else "Untitled"
            desc = desc_el.get_text(strip=True) if desc_el else ""
            link = f"https://www.skywalker.gr{title_el['href']}" if title_el else URL
            jobs.append({
                "platform": "Skywalker",
                "title": title,
                "description": desc,
                "original_url": link,
                "budget_amount": 0,
                "budget_currency": "EUR",
                "budget_usd": convert_to_usd(0, "EUR"),
                "created_at": datetime.now(timezone.utc)
            })
    except Exception as e:
        log.error(f"Fetch error: {e}")
    return jobs
