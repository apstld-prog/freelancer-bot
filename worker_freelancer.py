# worker_freelancer.py â€” FULL VERSION (deduplication + keyword + USD + posted time)

import os
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
import httpx
from db import get_session
from db_events import record_event
from db_keywords import list_keywords
from utils_fx import convert_to_usd

log = logging.getLogger("worker.freelancer")
logging.basicConfig(level=logging.INFO)

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
PLATFORM = "freelancer"
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))
KEYWORD_MODE = os.getenv("KEYWORD_FILTER_MODE", "on").lower() == "on"

def posted_ago(ts_str: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600} hours ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60} minutes ago"
        else:
            return "just now"
    except Exception:
        return "N/A"

def make_fingerprint(title: str, url: str) -> str:
    raw = f"{PLATFORM}|{title.strip()}|{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

async def fetch_freelancer_jobs():
    params = {
        "limit": 30,
        "sort_field": "time_submitted",
        "sort_direction": "desc",
        "full_description": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(API_URL, params=params)
        r.raise_for_status()
        return r.json().get("result", {}).get("projects", [])

async def process_jobs():
    from bot import build_application
    app = build_application()

    with get_session() as s:
        keywords = [k.keyword.lower() for k in list_keywords(s)]
    if not keywords:
        log.warning("No keywords found in database. Worker idle.")
        return

    jobs = await fetch_freelancer_jobs()
    count_new = 0

    with get_session() as s:
        for job in jobs:
            title = job.get("title", "").strip()
            desc = job.get("preview_description", "").strip()
            budget = job.get("budget", {}) or {}
            amount = budget.get("minimum", 0)
            currency = budget.get("currency", {}).get("code", "USD")
            url = f"https://www.freelancer.com/projects/{job.get('seo_url','')}"
            created_ts = job.get("submitdate") or job.get("time_submitted")
            posted = posted_ago(created_ts)

            fp = make_fingerprint(title, url)
            exists = s.execute(
                "SELECT 1 FROM job_fingerprints WHERE fingerprint=:fp",
                {"fp": fp}
            ).fetchone()
            if exists:
                continue

            match_kw = [k for k in keywords if k in title.lower() or k in desc.lower()]
            if KEYWORD_MODE and not match_kw:
                continue

            usd_amount = convert_to_usd(amount, currency)
            msg = (
                f"<b>{title}</b>\n"
                f"<b>Budget:</b> {amount} {currency} (~${usd_amount} USD)\n"
                f"<b>Source:</b> Freelancer\n"
                f"<b>Match:</b> {', '.join(match_kw) if match_kw else 'N/A'}\n"
                f"{desc[:400]}...\n"
                f"<i>Posted: {posted}</i>"
            )

            try:
                await app.bot.send_message(chat_id=os.getenv("ADMIN_IDS").split(",")[0],
                                           text=msg, parse_mode="HTML",
                                           disable_web_page_preview=True)
                s.execute(
                    "INSERT INTO job_fingerprints(fingerprint, platform, title, url, created_at) "
                    "VALUES (:fp, :p, :t, :u, NOW())",
                    {"fp": fp, "p": PLATFORM, "t": title, "u": url},
                )
                s.commit()
                count_new += 1
            except Exception as e:
                log.error("Send failed: %s", e)

    record_event(PLATFORM)
    log.info("âœ… %s cycle complete â€” %d new jobs sent", PLATFORM, count_new)

async def run_worker():
    log.info("ðŸš€ Starting %s worker...", PLATFORM)
    while True:
        try:
            await process_jobs()
        except Exception as e:
            log.error("Error in worker loop: %s", e)
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(run_worker())

