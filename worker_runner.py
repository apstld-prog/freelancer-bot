import asyncio
import logging
import os
import inspect
from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker")

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
sent_cache = {}


def make_job_key(job):
    """Generate a unique hashable job key."""
    try:
        url = job.get("url") or job.get("original_url") or job.get("affiliate_url")
        if url:
            return str(url).strip()
        combo = f"{job.get('platform','')}-{job.get('title','')}-{job.get('created_at','')}"
        return combo.strip()
    except Exception as e:
        logger.warning(f"[Worker] make_job_key error: {e}")
        return str(job)


async def run_fetch(func, kw):
    """Safely execute fetch function (async or sync)."""
    try:
        if inspect.iscoroutinefunction(func):
            return await func(kw)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, kw)
    except Exception as e:
        logger.warning(f"[Worker] Fetch error in {func.__name__}({kw}): {e}")
        return []


async def process_user(user_id: int, keywords: str):
    """Process a single user's keyword list."""
    try:
        keywords_list = [kw.strip() for kw in str(keywords).split(",") if kw.strip()]
        if not keywords_list:
            logger.info(f"[Worker] No keywords for user {user_id}")
            return

        logger.info(f"[Worker] Fetching jobs for user {user_id}: {','.join(keywords_list)}")

        # Prepare tasks for all platforms
        tasks = []
        for kw in keywords_list:
            tasks.append(run_fetch(fetch_freelancer_jobs, kw))
            tasks.append(run_fetch(fetch_pph_jobs, kw))
            tasks.append(run_fetch(fetch_skywalker_jobs, kw))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_jobs = []
        for res in results:
            if isinstance(res, list):
                all_jobs.extend(res)
            elif isinstance(res, Exception):
                logger.warning(f"[Worker] Exception in fetch: {res}")

        logger.info(f"[Worker] Total jobs merged for user {user_id}: {len(all_jobs)}")

        user_cache = sent_cache.setdefault(user_id, set())
        sent_count = 0

        for job in all_jobs:
            try:
                key = make_job_key(job)
                if not key or key in user_cache:
                    continue

                ok = await send_job_to_user(user_id, job)
                if ok:
                    user_cache.add(key)
                    sent_count += 1

                # Limit cache size per user
                if len(user_cache) > 300:
                    user_cache.clear()
            except Exception as e:
                logger.error(f"[Worker] Error sending job to {user_id}: {e}")

        logger.info(f"[Worker] ✅ Sent {sent_count} jobs to user {user_id}")

    except Exception as e:
        logger.error(f"[Worker] Critical error in process_user({user_id}): {e}")


async def main_loop():
    """Main worker loop."""
    while True:
        try:
            rows = get_user_list()
            logger.info(f"[Worker] Loaded {len(rows)} users")

            for row in rows:
                try:
                    user_id, keywords = row[0], row[1]
                    await process_user(int(user_id), str(keywords))
                except Exception as e:
                    logger.error(f"[Worker] Error processing user row {str(row)}: {e}")

        except Exception as e:
            logger.error(f"[Worker main_loop] {e}")

        logger.info("[Worker] Cycle complete. Sleeping...")
        await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main_loop())
