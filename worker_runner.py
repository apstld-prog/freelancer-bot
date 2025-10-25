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
sent_cache = {}  # avoid duplicate sends per user


def to_safe_str(value):
    """Convert any value (even nested lists) safely to a flat string."""
    if isinstance(value, (list, tuple, set)):
        # flatten any nested structure
        flat = []
        for v in value:
            if isinstance(v, (list, tuple, set)):
                flat.extend(v)
            else:
                flat.append(v)
        return ", ".join(str(v) for v in flat if v)
    if isinstance(value, dict):
        return ", ".join(f"{k}:{v}" for k, v in value.items())
    if value is None:
        return ""
    return str(value).strip()


async def process_user(user):
    user_id, keywords_raw = user
    keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
    logger.info(f"[Worker] Fetching for user {user_id} (kw={','.join(keywords)})")

    # collect all jobs
    all_jobs = []
    tasks = [fetch_freelancer_jobs(kw) for kw in keywords] + \
            [fetch_pph_jobs(kw) for kw in keywords] + \
            [fetch_skywalker_jobs(kw) for kw in keywords]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, list):
            all_jobs.extend(res)
        else:
            logger.warning(f"[Worker] Exception in fetch: {res}")

    logger.info(f"[Worker] Total jobs merged: {len(all_jobs)}")

    user_cache = sent_cache.setdefault(user_id, set())
    sent_count = 0

    for job in all_jobs:
        # always normalize url fields
        job_url = job.get("url") or job.get("original_url") or ""
        job_url = to_safe_str(job_url)
        if not job_url:
            continue

        # duplicate prevention
        if job_url in user_cache:
            continue

        ok = await send_job_to_user(user_id, job)
        if ok:
            # ✅ force string here before caching
            user_cache.add(to_safe_str(job_url))
            sent_count += 1

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
