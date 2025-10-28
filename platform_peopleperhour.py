# ======================================================
# platform_peopleperhour.py — Fetch jobs from PeoplePerHour RSS
# ======================================================
import logging
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger("platform_pph")

RSS_URL = "https://www.peopleperhour.com/rss/job-listings"

def fetch_pph_jobs(keywords):
    """Fetch and parse PeoplePerHour RSS feed, filter by keywords."""
    all_jobs = []
    try:
        r = httpx.get(RSS_URL, timeout=20)
        if r.status_code != 200:
            logger.warning(f"[PPH] HTTP {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "xml")
        items = soup.find_all("item")
        for item in items:
            title = (item.title.text or "").strip()
            desc = (item.description.text or "").strip()
            link = (item.link.text or "").strip()
            pub_date = item.pubDate.text if item.pubDate else None

            # Normalize
            pub_dt = None
            if pub_date:
                try:
                    pub_dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
                except Exception:
                    pass

            text_all = (title + " " + desc).lower()
            for kw in keywords:
                if kw.lower() in text_all:
                    all_jobs.append({
                        "platform": "PeoplePerHour",
                        "title": title,
                        "description": desc,
                        "budget": "N/A",
                        "currency": "GBP",
                        "created_at": pub_dt.isoformat() if pub_dt else None,
                        "url": link,
                        "keyword": kw
                    })
                    break
    except Exception as e:
        logger.error(f"[PPH] fetch error: {e}")
    return all_jobs
