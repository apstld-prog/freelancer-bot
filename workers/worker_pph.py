import time
import logging
import os
import requests
from bs4 import BeautifulSoup

from db import get_session, close_session
from db_keywords import get_keywords_for_user
from db_events import record_event
from utils import send_job_to_user

log = logging.getLogger("worker.pph")

INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

BASE_URL = "https://www.peopleperhour.com/freelance-jobs?search="


def fetch_pph(keyword: str):
    """
    Scrapes PeoplePerHour for matching jobs.
    """
    url = BASE_URL + requests.utils.quote(keyword)
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = soup.select("li.project")

    jobs = []

    for item in results:
        try:
            title_el = item.select_one("h3 a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = "https://www.peopleperhour.com" + title_el.get("href")

            desc_el = item.select_one(".project__description")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            budget_el = item.select_one(".project__budget")
            budget_text = budget_el.get_text(strip=True) if budget_el else None

            amount = None
            currency = None

            if budget_text:
                # Examples that originally may appear corrupted:
                # "Ã‚Â£50", "Ã¢â€šÂ¬120", "$300"
                txt = budget_text.strip()

                try:
                    currency = txt[0]
                    amount = int("".join(c for c in txt[1:] if c.isdigit()))
                except Exception:
                    amount = None
                    currency = None

            job_id = link.split("-")[-1]

            jobs.append({
                "job_id": job_id,
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": link,
                "budget_amount": amount,
                "budget_currency": currency
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
            jobs = fetch_pph(kw)
            if not jobs:
                continue

            for job in jobs:
                event = {
                    "platform": "pph",
                    "job_id": job["job_id"],
                    "telegram_id": telegram_id,
                    "title": job["title"],
                    "description": job["description"],
                    "original_url": job["original_url"],
                    "affiliate_url": job["affiliate_url"],
                    "budget_amount": job["budget_amount"],
                    "budget_currency": job["budget_currency"],
                }

                if record_event(**event):
                    send_job_to_user(telegram_id, event)


def main_loop():
    log.info("Starting PeoplePerHour worker...")
    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f"Worker PPH error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main_loop()


