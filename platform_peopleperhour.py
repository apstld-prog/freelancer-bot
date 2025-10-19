import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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
                logger.info(f"[PPH] fetching {url}")
            r = httpx.get(url, timeout=15)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            job_blocks = soup.select("a.job__title-link")

            for link in job_blocks:
                title = link.get_text(strip=True)
                job_url = "https://www.peopleperhour.com" + link["href"]
                desc_tag = link.find_parent("div", class_="job__container")
                desc = desc_tag.get_text(strip=True) if desc_tag else ""
                budget_tag = soup.select_one(".job__price, .job__budget")
                budget_text = budget_tag.get_text(strip=True) if budget_tag else ""
                currency, amount = None, None
                m = re.search(r"([£$€])\s?(\d+[\d,.]*)", budget_text)
                if m:
                    currency, amount = m.group(1), m.group(2)

                results.append({
                    "platform": "peopleperhour",
                    "title": title,
                    "description": desc,
                    "affiliate_url": job_url,
                    "original_url": job_url,
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
