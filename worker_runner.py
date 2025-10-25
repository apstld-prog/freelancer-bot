import asyncio
import logging
import os
from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from utils import send_job_to_user
from telegram import Bot

logger = logging.getLogger("worker")

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)

async def main_loop():
    if not TOKEN:
        print("[Worker] ERROR: Missing TELEGRAM_BOT_TOKEN environment variable.")
        return
    bot = Bot(token=TOKEN)
    print(f"[Worker] Using Telegram token from environment. Interval={WORKER_INTERVAL}s")

    while True:
        users = get_user_list()
        for user in users:
            for kw in user["keywords"]:
                f_jobs = await fetch_freelancer_jobs(kw)
                p_jobs = await fetch_pph_jobs(kw)
                for job in f_jobs + p_jobs:
                    await send_job_to_user(bot, user["user_id"], job)
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
