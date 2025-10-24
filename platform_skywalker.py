import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import logging

log = logging.getLogger("skywalker")

BASE_URL = "https://www.skywalker.gr/el/thesis-ergasias"


def fetch_skywalker_jobs(keywords):
    jobs = []
    try:
        log.info(f"[Skywalker] Fetching {BASE_URL}")
        r = httpx.get(BASE_URL, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.select("div.job-item") or soup.select("article.job")
        if not cards:
            log.info("[Skywalker] Found 0 raw listings")
            return []

        for card in cards:
            title_tag = card.select_one("a.job-title, a")
            title = title_tag.get_text(strip=True) if title_tag else "Untitled"
            link = title_tag["href"] if title_tag and title_tag.has_attr("href") else None
            if link and not link.startswith("http"):
                link = "https://www.skywalker.gr" + link

            desc_tag = card.select_one(".job-description, p")
            desc = desc_tag.get_text(strip=True) if desc_tag else ""

            created_at = datetime.now(timezone.utc)

            job = {
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": link,
                "source": "Skywalker",
                "budget_amount": None,
                "budget_currency": None,
                "created_at": created_at,
            }

            if any(kw.lower() in (title.lower() + desc.lower()) for kw in keywords):
                jobs.append(job)

        log.info(f"[Skywalker parsed {len(jobs)} entries after filtering]")
        return jobs

    except Exception as e:
        log.warning(f"[Skywalker error: {e}]")
        return []
