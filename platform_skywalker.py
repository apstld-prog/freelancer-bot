import logging
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def fetch_skywalker_jobs():
    """Fetch latest jobs from Skywalker Greece"""
    try:
        url = "https://www.skywalker.gr/elGR/jobs"
        jobs = []
        with httpx.Client(timeout=25) as client:
            r = client.get(url)
            if r.status_code != 200:
                logging.warning(f"[Skywalker] HTTP {r.status_code}")
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            for card in soup.select(".job"):
                title = card.select_one(".title")
                desc = card.select_one(".description")
                link = card.select_one("a")
                if not title or not link:
                    continue
                created_at = datetime.utcnow()
                jobs.append({
                    "id": link["href"].split("/")[-1],
                    "title": title.text.strip(),
                    "description": desc.text.strip() if desc else "",
                    "budget_amount": 0,
                    "budget_currency": "EUR",
                    "original_url": f"https://www.skywalker.gr{link['href']}",
                    "platform": "Skywalker",
                    "created_at": created_at
                })
        logging.info(f"[Skywalker] ✅ Collected {len(jobs)} jobs")
        return jobs
    except Exception as e:
        logging.error(f"[Skywalker] Exception: {e}")
        return []
