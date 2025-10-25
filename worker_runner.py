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
        return "|".join(to_hashable(v) for v in value)
    if isinstance(value, dict):
        return "&".join(f"{k}={to_hashable(v)}" for k, v in sorted(value.items()))
    if value is None:
        return ""
    return str(value).strip()


def normalize_user(raw_user):
    """Ensure (user_id:int, keywords:str)."""
    try:
        user_id, keywords_raw = raw_user
    except Exception:
        return None

    # Normalize ID
    if isinstance(user_id, (list, tuple)):
        user_id = user_id[0] if user_id else 0
    try:
        user_id = int(user_id)
    except Exception:
        return None

    # Normalize keywords
    if isinstance(keywords_raw, list):
        keywords_raw = ",".join(map(str, keywords_raw))
    else:
        keywords_raw = str(keywords_raw)
    return (user_id, keywords_raw)


def make_job_key(job: dict) -> str:
    """Stable unique key for job de-duplication."""
    url = job.get("url") or job.get("original_url") or job.get("affiliate_url") or ""
    if url:
        return to_hashable(url)
    platform = job.get("platform") or job.get("source") or "job"
    title = job.get("title") or ""
    posted = job.get("posted_at") or ""
    return to_hashable([platform, title, posted])


async def process_user(raw_user):
    user = normalize_user(raw_user)
    if not user:
        logger.warning(f"[Worker] Skipping malformed user row: {raw_user}")
        return

    user_id, keywords_str = user
    keywords = [kw.strip() for kw in str(keywords_str).split(",") if kw.strip()]
    logger.info(f"[Worker] Fetching for user {user_id} (kw={','.join(keywords)})")

    # Fetch concurrently from all platforms
    tasks = (
        [fetch_freelancer_jobs(kw) for kw in keywords] +
        [fetch_pph_jobs(kw) for kw in keywords] +
        [fetch_skywalker_jobs(kw) for kw in keywords]
    )
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
        job_key = make_job_key(job)
        if not job_key or job_key in user_cache:
            continue
        ok = await send_job_to_user(user_id, job)
        if ok:
            user_cache.add(job_key)
            sent_count += 1
        if len(user_cache) > 300:
            user_cache.clear()

    logger.info(f"[Worker] ✅ Sent {sent_count} jobs → {user_id}")


async def main_loop():
    while True:
        try:
            rows = get_user_list()
            users = [normalize_user(r) for r in rows if normalize_user(r)]
            logger.info(f"[Worker] Total users: {len(users)}")

            for u in users:
                try:
                    await process_user(u)
                except Exception as e:
                    # ✅ FIX: Force string conversion before logging
                    u_str = str(u)
                    e_str = str(e)
                    logger.error(f"[Worker] Error processing user {u_str}: {e_str}")
        except Exception as e:
            logger.error(f"[Worker main_loop error] {e}")
        logger.info("[Worker] Cycle complete. Sleeping...")
        await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main_loop())
