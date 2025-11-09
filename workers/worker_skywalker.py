import time
import logging
import os
import requests
from bs4 import BeautifulSoup

from db import get_session, close_session
from db_keywords import get_keywords_for_user
from db_events import record_event
from utils import send_job_to_user

log = logging.getLogger("worker.skywalker")

INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

BASE_URL = "https://www.skywalker.gr/el/aggelies-ergasias?keywords="


def fetch_skywalker(keyword: str):
    """
    Scrapes Skywalker job listings based on the keyword.
    """
    url = BASE_URL + requests.utils.quote(keyword)
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.job-item")
    jobs = []

    for item in items:
        try:
            title_el = item.select_one("a.job-title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = "https://www.skywalker.gr" + title_el.get("href")

            desc_el = item.select_one("div.job-description")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            job_id = link.split("/")[-1].split("-")[0]

            jobs.append({
                "job_id": job_id,
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": link,
                "budget_amount": None,
                "budget_currency": None,
            })
        except Exception:
            continue

    return jobs


def run_once():
    db = get_session()

    try:
        users = db.execute("SELECT telegram_id FROM users").fetchall()
    finally:
        close_session(db)

    for (telegram_id,) in users:
        keywords = get_keywords_for_user(telegram_id)
        if not keywords:
            continue

        for kw in keywords:
            jobs = fetch_skywalker(kw)
            if not jobs:
                continue

            for job in jobs:
                event = {
                    "platform": "skywalker",
                    "job_id": job["job_id"],
                    "telegram_id": telegram_id,
                    "title": job["title"],
                    "description": job["description"],
                    "original_url": job["original_url"],
                    "affiliate_url": job["affiliate_url"],
                    "budget_amount": None,
                    "budget_currency": None,
                }

                if record_event(**event):
                    send_job_to_user(telegram_id, event)


def main_loop():
    log.info("🚀 Starting Skywalker worker...")
    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f"Worker Skywalker error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main_loop()


