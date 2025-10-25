import asyncio
import os
import logging
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

sent_cache = {}

def make_job_key(job):
    url = job.get("affiliate_url") or job.get("original_url") or job.get("url")
    return url

async def process_user(user_id, keywords):
    for keyword in keywords:
        freelancer_jobs = await fetch_freelancer_jobs(keyword)
        pph_jobs = await fetch_pph_jobs(keyword)
        all_jobs = freelancer_jobs + pph_jobs
        for job in all_jobs:
            key = make_job_key(job)
            if not key or key in sent_cache:
                continue
            sent_cache[key] = True
            await send_job_to_user(BOT_TOKEN, user_id, job)
            await asyncio.sleep(2.5)

async def main_loop():
    while True:
        users = get_user_list()
        for user_id, keywords in users:
            try:
                await process_user(user_id, keywords)
            except Exception as e:
                logger.error(f"[Worker] Critical error in process_user({user_id}): {e}")
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    print(f"[Worker] Using Telegram token from environment. Interval={WORKER_INTERVAL}s")
    asyncio.run(main_loop())
