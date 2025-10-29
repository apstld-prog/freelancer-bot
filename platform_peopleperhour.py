import logging
import httpx
from datetime import datetime, timezone, timedelta
from currency_usd import usd_line
from bs4 import BeautifulSoup

logger = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"


def _parse_posted_ago(dt_str: str) -> str:
    try:
        dt = datetime.strptime(dt_str, "%d %b %Y")
        delta = datetime.now() - dt
        if delta.days < 1:
            return "today"
        elif delta.days == 1:
            return "1 day ago"
        else:
            return f"{delta.days} days ago"
    except Exception:
        return "N/A"


def fetch_pph_jobs(keywords: list[str]) -> list[dict]:
    try:
        logger.info("[PPH] Fetching latest jobs...")
        jobs = []

        with httpx.Client(timeout=30.0) as client:
            r = client.get(BASE_URL)
            r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".job-list .job")
        logger.info(f"[PPH] ✅ {len(cards)} jobs fetched")

        for card in cards:
            title = card.select_one(".job-title a")
            desc = card.select_one(".job-description")
            price = card.select_one(".job-price")
            date = card.select_one(".job-posted")

            title_text = title.text.strip() if title else "No title"
            desc_text = desc.text.strip() if desc else ""
            budget_text = price.text.strip() if price else "N/A"
            posted_ago = _parse_posted_ago(date.text.strip()) if date else "N/A"

            usd_info = usd_line(budget_text)
            matched_kw = None
            if keywords:
                text = f"{title_text} {desc_text}".lower()
                for kw in keywords:
                    if kw.lower() in text:
                        matched_kw = kw
                        break

            job = {
                "platform": "PeoplePerHour",
                "title": title_text,
                "description": desc_text,
                "budget": usd_info,
                "currency": "GBP",
                "min_amount": None,
                "max_amount": None,
                "created_at": datetime.now(timezone.utc),
                "posted_ago": posted_ago,
                "url": title["href"] if title and title.has_attr("href") else BASE_URL,
                "keyword": matched_kw or "N/A",
            }
            jobs.append(job)

        return jobs

    except Exception as e:
        logger.error(f"[PPH] Error: {e}")
        return []
