import asyncio
import logging
import os
from datetime import datetime, timezone
from db_events import ensure_feed_events_schema, save_feed_event
from utils import fetch_json, get_all_active_users, send_job_to_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_pph")

API_URL = "https://www.peopleperhour.com/api/v1/projects"

async def process_jobs():
    logger.info("[PPH Worker] Started")
    ensure_feed_events_schema()

    users = get_all_active_users()
    if not users:
        logger.warning("[PPH] No active users found.")
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
        logger.warning("[PPH] No keywords available.")
        return

    params = {"query": keywords, "page": 1}
    data = await fetch_json(API_URL, params)
    projects = data.get("projects", [])
    logger.info(f"[PPH] ✅ {len(projects)} jobs fetched")

    for job in projects:
        job_id = job.get("id")
        title = job.get("title", "")
        description = job.get("description", "")
        budget = job.get("budget", {}).get("amount", "N/A")
        currency = job.get("budget", {}).get("currency", "")
        link = f"https://www.peopleperhour.com/job/{job_id}"

        save_feed_event("pph", title, description, link, budget, currency)
        message = f"💼 <b>{title}</b>\n💰 {budget} {currency}\n🔗 {link}"

        for user in users:
            tg_id = user.get("telegram_id")
            if not tg_id:
                logger.warning(f"[send_job_to_user] Skipping invalid user without telegram_id: {user}")
                continue
            try:
                await send_job_to_user(None, int(tg_id), message, job)
            except Exception as e:
                logger.error(f"[PPH] Error sending to user {tg_id}: {e}")

async def main():
    while True:
        await process_jobs()
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", 120)))

if __name__ == "__main__":
    asyncio.run(main())
