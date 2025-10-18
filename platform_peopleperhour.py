
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)

def fetch_jobs(keywords):
    collected = []
    base_url = "https://www.peopleperhour.com/freelance-jobs?search={kw}"

    for kw in keywords:
        try:
            u = base_url.format(kw=kw)
            log.debug(f"PPH debug: keyword='{kw}', url='{u}'")
            with httpx.Client(timeout=10) as client:
                resp = client.get(u)
            log.debug(f"PPH debug: status={resp.status_code}")

            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".job-card, .freelance-job-card")
            log.debug(f"PPH debug: keyword='{kw}', cards_found={len(cards)}")

            for c in cards:
                title = c.select_one(".job-title, h3")
                desc = c.select_one(".job-description, p")
                budget = c.select_one(".job-budget")
                link = c.select_one("a[href]")
                job = {
                    "platform": "peopleperhour",
                    "title": title.text.strip() if title else "No title",
                    "description": desc.text.strip() if desc else "",
                    "budget_amount": budget.text.strip() if budget else None,
                    "budget_currency": "GBP",
                    "affiliate_url": link['href'] if link else None,
                    "original_url": link['href'] if link else None,
                    "created_at": datetime.utcnow().isoformat(),
                    "keyword": kw,
                }
                collected.append(job)

        except Exception as e:
            log.error(f"PPH debug: error on keyword '{kw}': {e}")

    log.info(f"PPH debug: total {len(collected)} jobs from {len(keywords)} keywords")
    return collected
