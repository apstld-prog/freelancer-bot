import logging
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger("platform_skywalker")
RSS_URL = "https://www.skywalker.gr/rss/latestjobs"


def fetch_skywalker_jobs(keywords):
    """Fetch Skywalker RSS job feed"""
    all_jobs = []
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(RSS_URL)
            if resp.status_code != 200:
                logger.warning(f"[Skywalker] HTTP {resp.status_code}")
                return []

            # 🧩 FIX: use html.parser instead of xml
            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.find_all("item")

            for item in items:
                title = item.find("title").text.strip() if item.find("title") else ""
                desc = item.find("description").text.strip() if item.find("description") else ""
                link = item.find("link").text.strip() if item.find("link") else ""
                pub_date = item.find("pubDate").text.strip() if item.find("pubDate") else ""
                created_at = _parse_rss_date(pub_date)

                if (datetime.utcnow() - created_at) > timedelta(hours=48):
                    continue

                kw = _match_keyword(title, desc, keywords)
                if not kw:
                    continue

                job = {
                    "title": title,
                    "description": desc,
                    "budget_amount": 0,
                    "budget_currency": "EUR",
                    "budget_usd": 0,
                    "created_at": created_at,
                    "platform": "Skywalker",
                    "matched_keyword": kw,
                    "original_url": link,
                }
                all_jobs.append(job)

        logger.info(f"[Skywalker] ✅ {len(all_jobs)} jobs fetched")
    except Exception as e:
        logger.warning(f"[Skywalker] ⚠️ Error: {e}")
    return all_jobs


def _parse_rss_date(pub_date):
    try:
        return datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _match_keyword(title, desc, keywords):
    text = (title + " " + desc).lower()
    for kw in keywords:
        if kw.lower() in text:
            return kw
    return ""
