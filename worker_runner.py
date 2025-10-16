import os
import time
import httpx
import json
from html import escape as _esc
from datetime import datetime

# -----------------------------------------------------
# Helper για ασφαλές HTML encoding (σταματά τα 400 Bad Request)
def _h(s: str) -> str:
    return _esc((s or "").strip(), quote=False)

# -----------------------------------------------------
# Περιβάλλον / σταθερές
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("ADMIN_TELEGRAM_ID")
FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"
INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))
QUERY = os.getenv("SEARCH_QUERY", "lighting,led")

# -----------------------------------------------------
def fetch_jobs():
    """Fetch latest jobs from Freelancer API"""
    try:
        with httpx.Client(timeout=15) as c:
            params = {
                "full_description": "false",
                "job_details": "false",
                "limit": 5,
                "offset": 0,
                "sort_field": "time_submitted",
                "sort_direction": "desc",
                "query": QUERY
            }
            r = c.get(FREELANCER_API, params=params)
            r.raise_for_status()
            data = r.json()
            return data.get("result", {}).get("projects", [])
    except Exception as e:
        print("Error fetching jobs:", e)
        return []

# -----------------------------------------------------
def send_job(job):
    """Send one job to Telegram"""
    try:
        title = _h(job.get("title"))
        desc = _h(job.get("preview_description", ""))[:300]
        currency = job.get("currency", {}).get("code", "")
        budget_min = job.get("budget", {}).get("minimum")
        budget_max = job.get("budget", {}).get("maximum")

        if budget_min and budget_max:
            budget = f"{budget_min}–{budget_max} {currency}"
        elif budget_min:
            budget = f"{budget_min} {currency}"
        else:
            budget = "N/A"

        budget = _h(budget)

        url = f"https://www.freelancer.com/projects/{job.get('seo_url') or ''}"
        url = _h(url)

        text = (
            f"<b>{title}</b>\n"
            f"{desc}\n\n"
            f"<b>💰 Budget:</b> {budget}\n"
            f"<b>🔗 Link:</b> {url}"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📄 Proposal", "url": url},
                    {"text": "🔗 Original", "url": url}
                ],
                [{"text": "💾 Save", "callback_data": "job:save"}]
            ]
        }

        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(keyboard)
        }

        r = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload,
            timeout=15
        )

        if r.status_code != 200:
            print("SendMessage failed:", r.text)

    except Exception as e:
        print("Error sending job:", e)

# -----------------------------------------------------
def main():
    print(f"[Worker] Running with interval={INTERVAL}s query='{QUERY}'")
    while True:
        jobs = fetch_jobs()
        if not jobs:
            print("No jobs fetched.")
        else:
            print(f"Fetched {len(jobs)} jobs")
            for job in jobs:
                send_job(job)
        time.sleep(INTERVAL)

# -----------------------------------------------------
if __name__ == "__main__":
    main()
