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

# Avoid duplicates
sent_cache = {}


def make_job_key(job):
    """Generate a unique key for caching jobs."""
    url = job.get("url") or job.get("original_url") or job.get("affiliate_url")
    if url:
        return str(url).strip()
    return f"{job.get('platform','')}-{job.get('title','')}-{job.get('posted_at','')}"


async def process_user(user_id: int, keywords: str):
    """Process jobs for one user safely."""
    try:
        keywords_list = [kw.strip() for kw in str(keywords).split(",") if kw.strip()]
        if not keywords_list:
            logger.info(f"[Worker] No keywords for user {user_id}")
            return

        logger.info(f"[Worker] Fetching jobs for {user_id}: {','.join(keywords_list)}")

        async def run_fetch_sync(func, kw):
            """Run sync fetch function in a thread."""
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, kw)

        tasks = []
        for kw in keywords_list:
            tasks.append(run_fetch_sync(fetch_freelancer_jobs, kw))
            tasks.append(run_fetch_sync(fetch_pph_jobs, kw))
            tasks.append(run_fetch_sync(fetch_skywalker_jobs, kw))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs = []
        for res in results:
            if isinstance(res, list):
                all_jobs.extend(res)
            elif isinstance(res, Exception):
                logger.warning(f"[Worker] Exception in fetch: {res}")

        logger.info(f"[Worker] Total jobs merged for {user_id}: {len(all_jobs)}")

        user_cache = sent_cache.setdefault(user_id, set())
        sent_count = 0

        for job in all_jobs:
            key = make_job_key(job)
            if not key or key in user_cache:
                continue
            ok = await send_job_to_user(user_id, job)
            if ok:
                user_cache.add(key)
                sent_count += 1
            if len(user_cache) > 300:
                user_cache.clear()

        logger.info(f"[Worker] ✅ Sent {sent_count} jobs → {user_id}")

    except Exception as e:
        logger.error(f"[Worker] Critical error in process_user({user_id}): {e}")


async def main_loop():
    """Main infinite loop."""
    while True:
        try:
            rows = get_user_list()
            logger.info(f"[Worker] Loaded {len(rows)} users")

            for row in rows:
                try:
                    user_id, keywords = row[0], row[1]
                    await process_user(int(user_id), str(keywords))
                except Exception as e:
                    logger.error(f"[Worker] Error processing row {str(row)}: {e}")

        except Exception as e:
            logger.error(f"[Worker main_loop] {e}")

        logger.info("[Worker] Cycle complete. Sleeping...")
        await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main_loop())
