import asyncio
import logging
import os
from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker")

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

# Cache to prevent duplicate job sends (per user)
sent_cache = {}

async def process_user(user):
    """Fetch and send jobs for a single user, filtering out duplicates."""
    user_id, keywords_raw = user
    keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
    logger.info(f"[Worker] Fetching for user {user_id} (kw={','.join(keywords)})")

    all_jobs = []
    freelancer_tasks = [fetch_freelancer_jobs(kw) for kw in keywords]
    pph_tasks = [fetch_pph_jobs(kw) for kw in keywords]
    skywalker_tasks = [fetch_skywalker_jobs(kw) for kw in keywords]

    results = await asyncio.gather(*(freelancer_tasks + pph_tasks + skywalker_tasks), return_exceptions=True)

    for res in results:
        if isinstance(res, list):
            all_jobs.extend(res)
        else:
            logger.warning(f"[Worker] Exception in fetch: {res}")

    logger.info(f"[Worker] Total jobs merged: {len(all_jobs)}")

    user_cache = sent_cache.setdefault(user_id, set())
    sent_count = 0

    for job in all_jobs:
        job_url = job.get("url") or job.get("original_url") or ""
        # ✅ Fix: ensure job_url is always a string
        if isinstance(job_url, list):
            job_url = job_url[0] if job_url else ""
        job_url = str(job_url).strip()

        if not job_url:
            continue
        if job_url in user_cache:
            continue  # skip duplicates

        ok = await send_job_to_user(user_id, job)
        if ok:
            user_cache.add(job_url)
            sent_count += 1

        # limit cache size
        if len(user_cache) > 300:
            user_cache.clear()

    logger.info(f"[Worker] ✅ Sent {sent_count} jobs → {user_id}")

async def main_loop():
    """Main worker loop."""
    while True:
        try:
            users = get_user_list()
            logger.info(f"[Worker] Total users: {len(users)}")
            for user in users:
                try:
                    await process_user(user)
                except Exception as e:
                    logger.error(f"[Worker] Error processing user {user}: {e}")
        except Exception as e:
            logger.error(f"[Worker main_loop error] {e}")
        logger.info("[Worker] Cycle complete. Sleeping...")
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
