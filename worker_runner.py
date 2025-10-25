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
sent_cache = {}

def to_hashable(value):
    """Convert any value (even nested) to a hashable string."""
    if isinstance(value, (list, tuple, set)):
        flat = []
        for v in value:
            flat.append(to_hashable(v))
        return ",".join(flat)
    elif isinstance(value, dict):
        return ",".join(f"{k}:{to_hashable(v)}" for k, v in sorted(value.items()))
    elif value is None:
        return ""
    else:
        return str(value).strip()

async def process_user(user):
    user_id, keywords_raw = user
    keywords = [kw.strip() for kw in str(keywords_raw).split(",") if kw.strip()]
    logger.info(f"[Worker] Fetching for user {user_id} (kw={','.join(keywords)})")

    # fetch from all platforms
    tasks = [
        *[fetch_freelancer_jobs(kw) for kw in keywords],
        *[fetch_pph_jobs(kw) for kw in keywords],
        *[fetch_skywalker_jobs(kw) for kw in keywords],
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs = []
    for res in results:
        if isinstance(res, list):
            all_jobs.extend(res)
        else:
            logger.warning(f"[Worker] Exception in fetch: {res}")

    logger.info(f"[Worker] Total jobs merged: {len(all_jobs)}")

    user_cache = sent_cache.setdefault(user_id, set())
    sent_count = 0

    for job in all_jobs:
        # normalize and hash URL
        job_url = to_hashable(job.get("url") or job.get("original_url") or "")
        if not job_url:
            continue

        # prevent duplicates
        if job_url in user_cache:
            continue

        ok = await send_job_to_user(user_id, job)
        if ok:
            user_cache.add(job_url)
            sent_count += 1

        # clear cache if too large
        if len(user_cache) > 300:
            user_cache.clear()

    logger.info(f"[Worker] ✅ Sent {sent_count} jobs → {user_id}")

async def main_loop():
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
