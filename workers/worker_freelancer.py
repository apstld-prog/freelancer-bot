import asyncio
import logging
import os
from datetime import datetime, timezone
from db_events import ensure_feed_events_schema, save_feed_event
from utils import fetch_json, get_all_active_users, send_job_to_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_freelancer")

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

async def process_jobs():
    logger.info("[Freelancer Worker] Started")
    ensure_feed_events_schema()

    users = get_all_active_users()
    if not users:
        logger.warning("[Freelancer] No active users found.")
        return

    keywords = ",".join(
        list(
            {
                kw["keyword"]
                for u in users
                for kw in u.get("keywords", [])
                if kw.get("keyword")
            }
        )
    )

    if not keywords:
        logger.warning("[Freelancer] No keywords available.")
        return

    params = {
        "limit": 30,
        "sort_field": "time_submitted",
        "sort_direction": "desc",
        "full_description": "false",
        "query": keywords,
    }

    data = await fetch_json(API_URL, params)
    projects = data.get("result", {}).get("projects", [])
    logger.info(f"[Freelancer] ✅ {len(projects)} jobs fetched")

    for job in projects:
        job_id = job.get("id")
        title = job.get("title", "")
        description = job.get("preview_description", "")
        budget = job.get("budget", {}).get("minimum", "N/A")
        currency = job.get("currency", {}).get("code", "")
        link = f"https://www.freelancer.com/projects/{job_id}"

        save_feed_event("freelancer", title, description, link, budget, currency)

        message = f"💼 <b>{title}</b>\n💰 {budget} {currency}\n🔗 {link}"
        for user in users:
            tg_id = user.get("telegram_id")
            if not tg_id:
                logger.warning(f"[send_job_to_user] Skipping invalid user without telegram_id: {user}")
                continue
            try:
                await send_job_to_user(None, int(tg_id), message, job)
            except Exception as e:
                logger.error(f"[Freelancer] Error sending to user {tg_id}: {e}")

async def main():
    while True:
        await process_jobs()
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", 120)))

if __name__ == "__main__":
    asyncio.run(main())
