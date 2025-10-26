import asyncio
import os
import logging
from datetime import datetime, timezone
from utils import send_job_to_user
from db import get_user_list
from platform_peopleperhour import fetch_pph_jobs

logger = logging.getLogger("worker_pph")

PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))

def match_keyword(job, keyword):
    return keyword.lower() in job["title"].lower() or keyword.lower() in job["description"].lower()

async def process_user(user, keywords):
    try:
        jobs = await fetch_pph_jobs()
        logger.info(f"[PPH] {len(jobs)} jobs fetched for user {user['id']}")
        for kw in keywords:
            for job in jobs:
                if not match_keyword(job, kw):
                    continue
                job["keyword"] = kw
                job["posted_ago"] = "N/A"
                if job.get("created_at"):
                    try:
                        dt = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
                        delta = datetime.now(timezone.utc) - dt
                        hours = delta.total_seconds() // 3600
                        if hours < 1:
                            job["posted_ago"] = "just now"
                        elif hours < 24:
                            job["posted_ago"] = f"{int(hours)} hours ago"
                        else:
                            job["posted_ago"] = f"{int(hours//24)} days ago"
                    except Exception:
                        pass
                budget_amount = job.get("budget_amount")
                budget_currency = job.get("budget_currency")
                budget_usd = job.get("budget_usd")
                if budget_amount and budget_currency:
                    budget_str = f"{budget_currency} {budget_amount}"
                    if budget_usd:
                        budget_str += f" (~${budget_usd} USD)"
                else:
                    budget_str = "N/A"
                job["budget_str"] = budget_str
                await send_job_to_user(user["id"], job)
    except Exception as e:
        logger.error(f"Error in process_user: {e}")

async def main_loop():
    while True:
        users = get_user_list()
        logger.info(f"[PPH] Processing {len(users)} users...")
        for user in users:
            keywords = user.get("keywords", [])
            await process_user(user, keywords)
        await asyncio.sleep(PPH_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
