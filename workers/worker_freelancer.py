#!/usr/bin/env python3
import os
import time
import logging
import requests
from datetime import datetime, timezone

from db import get_session, close_session
from sqlalchemy import text
from db_events import record_event
from db_keywords import get_keywords
from utils import wrap_affiliate_link

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("freelancer_worker")

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"


def posted_ago(ts):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    diff = datetime.now(timezone.utc) - dt

    mins = int(diff.total_seconds() // 60)
    hrs = mins // 60
    days = hrs // 24

    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} minutes ago"
    if hrs < 24:
        return f"{hrs} hours ago"
    return f"{days} days ago"


def fetch_freelancer_jobs():
    params = {
        "limit": 30,
        "full_description": True,
        "job_details": True,
        "sort_field": "time_submitted",
        "sort_direction": "desc"
    }
    r = requests.get(API_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()["result"]["projects"]


def already_sent(user_id, job_id):
    db = get_session()
    try:
        r = db.execute(
            text("SELECT 1 FROM feed_event WHERE user_id=:u AND job_id=:j"),
            {"u": user_id, "j": job_id}
        ).fetchone()
        return bool(r)
    finally:
        close_session(db)


def send_job_card(chat_id, job, match_kw):
    budget_min = job.get("budget", {}).get("minimum")
    budget_max = job.get("budget", {}).get("maximum")
    currency = job.get("currency", {}).get("code", "USD")

    title = job.get("title", "Untitled")
    desc = job.get("preview_description", "")[:400]

    ts = job.get("time_submitted")
    ago = posted_ago(ts)

    budget_text = f"{budget_min}–{budget_max} {currency}"
    usd = job.get("budget", {}).get("minimum_usd")
    if usd:
        budget_text += f" ({usd}$)"

    msg = (
        f"*{title}*\n"
        f"🪙 *Budget:* {budget_text}\n"
        f"🌐 *Source:* Freelancer\n"
        f"🔍 *Match:* {match_kw}\n"
        f"📝 {desc}\n"
        f"🕒 {ago}"
    )

    jid = str(job["id"])

    kb = {
        "inline_keyboard": [
            [
                {"text": "Proposal", "url": wrap_affiliate_link(job["seo_url"])},
                {"text": "Original", "url": wrap_affiliate_link(job["seo_url"])}
            ],
            [
                {"text": "⭐ Save", "callback_data": f"act:save:{jid}"},
                {"text": "🗑️ Delete", "callback_data": f"act:del:{jid}"}
            ]
        ]
    }

    requests.post(CHAT_API, json={
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "reply_markup": kb
    })


def process_user_jobs(user_id):
    kws = get_keywords(user_id)
    if not kws:
        return

    jobs = fetch_freelancer_jobs()

    for job in jobs:
        jid = str(job["id"])
        fulltext = (job.get("title", "") + " " + job.get("preview_description", "")).lower()

        match = None
        for k in kws:
            if k.lower() in fulltext:
                match = k
                break

        if not match:
            continue

        if already_sent(user_id, jid):
            continue

        send_job_card(user_id, job, match)
        record_event(user_id, "freelancer", jid)


def get_all_users():
    db = get_session()
    try:
        rows = db.execute(text("SELECT telegram_id FROM app_user WHERE active=true")).fetchall()
        return [r[0] for r in rows]
    finally:
        close_session(db)


if __name__ == "__main__":
    log.info("✅ Freelancer worker started")

    while True:
        try:
            for uid in get_all_users():
                process_user_jobs(uid)
        except Exception as e:
            log.error(f"Worker error: {e}")

        time.sleep(60)

