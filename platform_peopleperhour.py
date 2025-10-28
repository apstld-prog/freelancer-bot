import logging
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def fetch_pph_jobs():
    """Fetch jobs from PeoplePerHour"""
    try:
        url = "https://www.peopleperhour.com/freelance-jobs"
        jobs = []
        with httpx.Client(timeout=25) as client:
            r = client.get(url)
            if r.status_code != 200:
                logging.warning(f"[PPH] HTTP {r.status_code}")
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            for card in soup.select(".job-card"):
                title = card.select_one(".job-title")
                desc = card.select_one(".job-desc")
                link = card.select_one("a.job-link")
                budget = card.select_one(".job-budget")
                if not title or not link:
                    continue
                created_at = datetime.utcnow()
                jobs.append({
                    "id": link["href"].split("/")[-1],
                    "title": title.text.strip(),
                    "description": desc.text.strip() if desc else "",
                    "budget_amount": float(budget.text.replace("$", "").strip()) if budget else 0,
                    "budget_currency": "USD",
                    "original_url": f"https://www.peopleperhour.com{link['href']}",
                    "platform": "PeoplePerHour",
                    "created_at": created_at
                })
        logging.info(f"[PPH] ✅ Collected {len(jobs)} jobs")
        return jobs
    except Exception as e:
        logging.error(f"[PPH] Exception: {e}")
        return []
