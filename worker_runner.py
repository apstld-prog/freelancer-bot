import asyncio
import os
import logging
from telegram import Bot
from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker")

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)

if not BOT_TOKEN:
    raise ValueError("[Worker] ❌ Missing Telegram bot token in environment variables")

bot = Bot(token=BOT_TOKEN)
sent_cache = {}

def make_job_key(job):
    """Generate a unique key for deduplication."""
    url = job.get("affiliate_url") or job.get("original_url") or job.get("url")
    return url

async def process_user(user_id, keywords):
    """Fetch and send jobs for a single user."""
    for keyword in keywords:
        try:
            freelancer_jobs = await fetch_freelancer_jobs(keyword)
            pph_jobs = await fetch_pph_jobs(keyword)
            all_jobs = freelancer_jobs + pph_jobs

            for job in all_jobs:
                key = make_job_key(job)
                if not key or key in sent_cache:
                    continue
                sent_cache[key] = True
                await send_job_to_user(bot, user_id, job)
                await asyncio.sleep(2.5)

        except Exception as e:
            logger.error(f"[Worker] Error processing user ({user_id}, '{keyword}'): {e}")

async def main_loop():
    """Main worker loop polling for users and jobs."""
    while True:
        users = get_user_list()
        logger.info(f"[Worker] Checking {len(users)} active users")
        for user_id, keywords in users:
            try:
                await process_user(user_id, keywords)
            except Exception as e:
                logger.error(f"[Worker] Critical error in process_user({user_id}): {e}")
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    print(f"[Worker] Using Telegram token from environment. Interval={WORKER_INTERVAL}s")
    try:
        asyncio.run(main_loop())
    except Exception as e:
        logger.critical(f"[Worker] Fatal error: {e}")
        raise
