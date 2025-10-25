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


def make_job_key(job):
    """Generate a unique hashable key for each job."""
    url = job.get("url") or job.get("original_url") or job.get("affiliate_url")
    if not url:
        return None
    return f"{job.get('platform','')}::{url}"


async def process_user(bot, user_id: int, keywords: str):
    """Process each user's keywords and send job alerts."""
    try:
        logger.info(f"[Worker] Processing user {user_id} with keywords: {keywords}")
        all_jobs = []

        for kw in [k.strip() for k in keywords.split(",") if k.strip()]:
            # fetch jobs per platform
            f_jobs = await fetch_freelancer_jobs(kw)
            p_jobs = await fetch_pph_jobs(kw)
            s_jobs = await fetch_skywalker_jobs(kw)

            all_jobs.extend(f_jobs + p_jobs + s_jobs)

        if not all_jobs:
            logger.info(f"[Worker] No jobs found for {user_id}")
            return

        sent_cache.setdefault(user_id, set())
        sent_count = 0
        for job in all_jobs:
            job_key = make_job_key(job)
            if not job_key or job_key in sent_cache[user_id]:
                continue

            await send_job_to_user(bot, user_id, job)
            sent_cache[user_id].add(job_key)
            sent_count += 1

        logger.info(f"[Worker] ✅ Sent {sent_count} jobs to {user_id}")

    except Exception as e:
        logger.error(f"[Worker] Critical error in process_user({user_id}): {e}")


async def worker_loop(bot):
    """Main worker loop."""
    while True:
        try:
            users = get_user_list()
            if not users:
                logger.warning("[Worker] No users found.")
            else:
                logger.info(f"[Worker] Processing {len(users)} users")
                tasks = []
                for user_id, keywords in users:
                    tasks.append(process_user(bot, int(user_id), str(keywords)))
                await asyncio.gather(*tasks)

            await asyncio.sleep(WORKER_INTERVAL)

        except Exception as e:
            logger.error(f"[Worker] Global error: {e}")
            await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    import telegram

    # Accept any of the three env var names
    TOKEN = (
        os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
        or os.getenv("BOT_TOKEN")
        or ""
    )

    if not TOKEN:
        print("[Worker] ERROR: Missing Telegram token. Set one of: TELEGRAM_BOT_TOKEN / TELEGRAM_TOKEN / BOT_TOKEN")
        raise SystemExit(1)

    # Log which one was used (without printing the token)
    used_name = (
        "TELEGRAM_BOT_TOKEN" if os.getenv("TELEGRAM_BOT_TOKEN") else
        "TELEGRAM_TOKEN" if os.getenv("TELEGRAM_TOKEN") else
        "BOT_TOKEN"
    )
    print(f"[Worker] Using Telegram token from {used_name}. Interval={WORKER_INTERVAL}s")

    bot = telegram.Bot(TOKEN)
    print("[Worker] Starting background process...")
    asyncio.run(worker_loop(bot))
