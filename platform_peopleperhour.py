import os, re, httpx
from datetime import datetime, timedelta
from urllib.parse import urlencode

def get_items(keywords=None, fresh_since=None, limit=20, logger=None):
    keywords = keywords or []
    jobs = []
    client = httpx.Client(timeout=15)

    for kw in keywords:
        try:
            url = f"https://www.peopleperhour.com/freelance-jobs?search={kw}"
            resp = client.get(url)
            if resp.status_code != 200:
                if logger: logger.warning(f"PPH: failed {url} ({resp.status_code})")
                continue

            text = resp.text
            matches = re.findall(r'<a[^>]+href="(/freelance-jobs/[^"]+)"[^>]*>(.*?)</a>', text)
            for href, title in matches:
                full_url = f"https://www.peopleperhour.com{href}"
                title_clean = re.sub(r"<.*?>", "", title).strip()
                if not title_clean: 
                    continue
                jobs.append({
                    "title": title_clean,
                    "original_url": full_url,
                    "platform": "peopleperhour",
                    "created_at": datetime.utcnow().isoformat(),
                    "budget_amount": None,
                    "budget_currency": "GBP",
                    "description": "",
                })
                if len(jobs) >= limit:
                    break

        except Exception as e:
            if logger: logger.error(f"PPH error for {kw}: {e}")

    if logger: logger.info(f"PPH fetched={len(jobs)}")
    return jobs
