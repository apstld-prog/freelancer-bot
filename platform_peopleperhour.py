import re
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def get_items(keywords=None, fresh_since=None, limit=50, logger=None):
    base_url = "https://www.peopleperhour.com/freelance-jobs?search="
    results = []

    if not keywords:
        keywords = ["freelance"]
    elif isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    for kw in keywords:
        url = f"{base_url}{kw}"
        try:
            if logger:
                logger.info(f"[PPH] fetching: {url}")
            r = httpx.get(url, timeout=15)
            if r.status_code != 200:
                if logger:
                    logger.warning(f"[PPH] HTTP {r.status_code} for {url}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            jobs = soup.select("section.job")
            for job in jobs:
                title_tag = job.select_one("h3 a")
                desc_tag = job.select_one(".job-description, .description")
                budget_tag = job.select_one(".job-budget, .job__price")

                title = title_tag.get_text(strip=True) if title_tag else "(No title)"
                url_job = "https://www.peopleperhour.com" + title_tag["href"] if title_tag and title_tag.has_attr("href") else url
                desc = desc_tag.get_text(strip=True) if desc_tag else ""
                budget_text = budget_tag.get_text(strip=True) if budget_tag else ""
                currency, amount = None, None
                m = re.search(r"([£$€])\s?(\d+[\d,.]*)", budget_text)
                if m:
                    currency, amount = m.group(1), m.group(2)

                results.append({
                    "platform": "peopleperhour",
                    "title": title,
                    "description": desc,
                    "affiliate_url": url_job,
                    "original_url": url_job,
                    "budget_amount": amount,
                    "budget_currency": currency,
                    "budget_usd": None,
                    "created_at": datetime.utcnow().isoformat()
                })

                if len(results) >= limit:
                    break

        except Exception as e:
            if logger:
                logger.error(f"[PPH] error fetching {kw}: {e}")

    if logger:
        logger.info(f"[PPH] total fetched={len(results)}")
    return results
