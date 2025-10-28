# ======================================================
# platform_skywalker.py — Fetch Greek jobs from Skywalker.gr
# ======================================================
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger("platform_skywalker")

RSS_URL = "https://www.skywalker.gr/rss/latestjobs"

def normalize(text):
    return (text or "").strip().lower()

def fetch_skywalker_jobs(keywords):
    """Fetch and parse Skywalker RSS feed, match greek or english keywords."""
    all_jobs = []
    try:
        r = httpx.get(RSS_URL, timeout=20)
        if r.status_code != 200:
            logger.warning(f"[Skywalker] HTTP {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "xml")
        items = soup.find_all("item")
        for item in items:
            title = normalize(item.title.text)
            desc = normalize(item.description.text)
            link = item.link.text.strip()
            date_text = item.pubDate.text if item.pubDate else None

            created_at = None
            if date_text:
                try:
                    created_at = datetime.strptime(date_text, "%a, %d %b %Y %H:%M:%S %z")
                except Exception:
                    pass

            combined = title + " " + desc
            for kw in keywords:
                kw_low = kw.lower()
                # check both greek/latin variants
                if kw_low in combined or kw_low.replace("φωτισμός", "lighting") in combined:
                    all_jobs.append({
                        "platform": "Skywalker",
                        "title": title,
                        "description": desc,
                        "budget": "N/A",
                        "currency": "EUR",
                        "created_at": created_at.isoformat() if created_at else None,
                        "url": link,
                        "keyword": kw
                    })
                    break
    except Exception as e:
        logger.error(f"[Skywalker] fetch error: {e}")
    return all_jobs
