import time
import logging
import os
import requests

from db import get_session, close_session
from db_keywords import get_keywords_for_user
from db_events import record_event
from utils import send_job_to_user

log = logging.getLogger("worker.freelancer")

INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

BASE_URL = (
    "https://www.freelancer.com/api/projects/0.1/projects/active/"
    "?full_description=false&job_details=false&limit=30&offset=0"
    "&sort_field=time_submitted&sort_direction=desc&query="
)


def fetch_freelancer(keyword: str):
    """Fetch jobs from Freelancer.com API for a given keyword."""
    try:
        url = BASE_URL + requests.utils.quote(keyword)
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []

    projects = data.get("result", {}).get("projects", [])
    jobs = []

    for p in projects:
        job_id = p.get("id")
        title = p.get("title", "")
        desc = p.get("preview_description", "")
        link = f"https://www.freelancer.com/projects/{job_id}"

        budget = p.get("budget", {})
        amount = budget.get("minimum")
        currency = budget.get("currency", {}).get("code")

        jobs.append({
            "job_id": job_id,
            "title": title,
            "description": desc,
            "original_url": link,
            "affiliate_url": link,  # Replace later with affiliate logic
            "budget_amount": amount,
            "budget_currency": currency
        })

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
            jobs = fetch_freelancer(kw)
            if not jobs:
                continue

            for job in jobs:
                event = {
                    "platform": "freelancer",
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
    log.info("🚀 Starting freelancer worker...")
    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f"Worker Freelancer error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main_loop()

