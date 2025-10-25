import asyncio
import logging
import os
from telegram import Bot

from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker")

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)
sent_cache = {}


async def process_keyword(bot, user, keyword):
    """Fetch and send jobs for a specific keyword."""
    all_jobs = []

    # Fetch jobs from both active platforms
    try:
        f_jobs = await fetch_freelancer_jobs(keyword)
        pph_jobs = await fetch_pph_jobs(keyword)
        sky_jobs = await fetch_skywalker_jobs(keyword)
        all_jobs = (f_jobs or []) + (pph_jobs or []) + (sky_jobs or [])
    except Exception as e:
        logger.error(f"[Worker] Fetch error for keyword '{keyword}': {e}")
        return

    for job in all_jobs:
        job["keyword"] = keyword  # ✅ crucial: pass triggering keyword
        job_key = job.get("id") or job.get("url")

        if not job_key:
            continue
        cache_key = f"{user['user_id']}_{job_key}"
        if cache_key in sent_cache:
            continue

        sent_cache[cache_key] = True
        await send_job_to_user(bot, user["user_id"], job)
        await asyncio.sleep(1)  # small delay between sends


async def main_loop():
    if not TOKEN:
        logger.error("[Worker] ERROR: Missing TELEGRAM_BOT_TOKEN environment variable.")
        return

    bot = Bot(token=TOKEN)
    logger.info(f"[Worker] Using Telegram token from environment. Interval={WORKER_INTERVAL}s")
    logger.info("[Worker] Starting background process...")

    while True:
        try:
            users = get_user_list()
            for user in users:
                if not user.get("keywords"):
                    continue
                for kw in user["keywords"].split(","):
                    kw = kw.strip()
                    if not kw:
                        continue
                    await process_keyword(bot, user, kw)
        except Exception as e:
            logger.error(f"[Worker] Error in main loop: {e}")

        await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main_loop())
