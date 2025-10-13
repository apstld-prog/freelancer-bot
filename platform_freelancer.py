# platform_freelancer.py
import requests, datetime
from bs4 import BeautifulSoup
from config import FREELANCER_URL, convert_to_usd

def fetch_freelancer_jobs(limit=50):
    """Fetch job listings from Freelancer RSS."""
    url = f"{FREELANCER_URL}/rss.xml"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")

    jobs = []
    for item in soup.find_all("item")[:limit]:
        title = item.title.text.strip()
        link = item.link.text.strip()
        desc = item.description.text.strip()
        pub_date = item.pubDate.text.strip() if item.pubDate else None

        # Extract currency & budget
        budget_min, budget_max, currency = None, None, "USD"
        if "Budget:" in desc:
            try:
                part = desc.split("Budget:")[1].split("<")[0].strip()
                pieces = part.replace(",", "").split()
                if len(pieces) >= 2:
                    currency = pieces[0].upper()
                    budget_min = float(pieces[1])
                    if len(pieces) >= 3:
                        budget_max = float(pieces[2])
            except Exception:
                pass

        jobs.append({
            "source": "freelancer",
            "title": title,
            "description": desc,
            "original_url": link,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "currency": currency,
            "created_at": datetime.datetime.utcnow(),
        })
    return jobs
