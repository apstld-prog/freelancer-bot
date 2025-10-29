import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from currency_usd import usd_line

logger = logging.getLogger("platform_skywalker")

BASE_URL = "https://www.skywalker.gr/el/thesis"


def _parse_posted_ago(date_str: str) -> str:
    try:
        if "σήμερα" in date_str:
            return "today"
        if "χθες" in date_str:
            return "1 day ago"
        return date_str.strip()
    except Exception:
        return "N/A"


def fetch_skywalker_jobs(keywords: list[str]) -> list[dict]:
    try:
        logger.info("[Skywalker] Fetching jobs...")
        jobs = []

        with httpx.Client(timeout=30.0) as client:
            r = client.get(BASE_URL)
            r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".job-list-item")
        logger.info(f"[Skywalker] ✅ {len(cards)} jobs fetched")

        for card in cards:
            title_el = card.select_one("h2 a")
            desc_el = card.select_one(".job-desc")
            date_el = card.select_one(".job-date")

            title = title_el.text.strip() if title_el else "No title"
            desc = desc_el.text.strip() if desc_el else ""
            posted_ago = _parse_posted_ago(date_el.text) if date_el else "N/A"

            usd_info = usd_line()  # No budget info on Skywalker

            matched_kw = None
            if keywords:
                text = f"{title} {desc}".lower()
                for kw in keywords:
                    if kw.lower() in text:
                        matched_kw = kw
                        break

            job = {
                "platform": "Skywalker",
                "title": title,
                "description": desc,
                "budget": usd_info,
                "currency": "EUR",
                "min_amount": None,
                "max_amount": None,
                "created_at": datetime.now(timezone.utc),
                "posted_ago": posted_ago,
                "url": title_el["href"] if title_el and title_el.has_attr("href") else BASE_URL,
                "keyword": matched_kw or "N/A",
            }
            jobs.append(job)

        return jobs

    except Exception as e:
        logger.error(f"[Skywalker] Error: {e}")
        return []
