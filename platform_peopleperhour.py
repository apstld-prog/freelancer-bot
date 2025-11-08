import httpx, logging
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from utils_fx import convert_to_usd

log = logging.getLogger("worker.pph")
URL = "https://www.peopleperhour.com/freelance-jobs"

def fetch_pph_jobs():
    jobs = []
    try:
        r = httpx.get(URL, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("section.project")
        for c in cards:
            title_el = c.select_one("h5 a")
            desc_el = c.select_one(".project-about")
            budget_el = c.select_one(".project-price")
            title = title_el.get_text(strip=True) if title_el else "Untitled"
            desc = desc_el.get_text(strip=True) if desc_el else ""
            budget_text = budget_el.get_text(strip=True) if budget_el else ""
            amount, currency = parse_budget(budget_text)
            jobs.append({
                "platform": "PeoplePerHour",
                "title": title,
                "description": desc,
                "original_url": f"https://www.peopleperhour.com{title_el['href']}" if title_el else URL,
                "budget_amount": amount,
                "budget_currency": currency,
                "budget_usd": convert_to_usd(amount, currency),
                "created_at": datetime.now(timezone.utc)
            })
    except Exception as e:
        log.error(f"Fetch error: {e}")
    return jobs

def parse_budget(txt: str):
    """Extract numeric and currency info."""
    import re
    if not txt:
        return 0, "USD"
    m = re.search(r"(\d+)", txt.replace(",", ""))
    if not m:
        return 0, "USD"
    amount = int(m.group(1))
    cur = "GBP" if "Â£" in txt else "EUR" if "â‚¬" in txt else "USD"
    return amount, cur

