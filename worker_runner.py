import asyncio
import logging
import time
from datetime import datetime
from db_keywords import list_keywords
from utils_telegram import send_jobs_to_user
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

FREELANCER_INTERVAL = 60
PPH_INTERVAL = 300
SKYWALKER_INTERVAL = 300

last_run = {"freelancer": 0, "pph": 0, "skywalker": 0}


async def run_pipeline():
    from db import get_connection

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id FROM keyword")
    users = [r[0] for r in cur.fetchall()]
    conn.close()

    total_jobs = 0

    for user_id in users:
        if not isinstance(user_id, int) or user_id < 1000000000:
            logger.warning(f"[Worker] Skipping invalid user_id {user_id}")
            continue

        keywords = list_keywords(user_id)
        if not keywords:
            continue

        keywords_list = [k["keyword"] if isinstance(k, dict) else k for k in keywords]
        joined_keywords = ", ".join(keywords_list)
        logger.info(f"[Worker] Fetching jobs for user {user_id}: {joined_keywords}")

        now = time.time()

        # FREELANCER
        if now - last_run["freelancer"] >= FREELANCER_INTERVAL:
            try:
                freelancer_jobs = await asyncio.to_thread(fetch_freelancer_jobs, keywords_list)
                if freelancer_jobs:
                    await send_jobs_to_user(user_id, freelancer_jobs, "freelancer")
                    total_jobs += len(freelancer_jobs)
            except Exception as e:
                logger.warning(f"[Freelancer] fetch error: {e}")
            last_run["freelancer"] = now

        # PPH
        if now - last_run["pph"] >= PPH_INTERVAL:
            try:
                pph_jobs = fetch_pph_jobs(keywords_list)  # ✅ FIX: pass list, no await
                if pph_jobs:
                    await send_jobs_to_user(user_id, pph_jobs, "peopleperhour")
                    total_jobs += len(pph_jobs)
            except Exception as e:
                logger.warning(f"[PPH] fetch error: {e}")
            last_run["pph"] = now

        # SKYWALKER
        if now - last_run["skywalker"] >= SKYWALKER_INTERVAL:
            try:
                sky_jobs = fetch_skywalker_jobs(keywords_list)  # ✅ FIX: remove await
                if sky_jobs:
                    await send_jobs_to_user(user_id, sky_jobs, "skywalker")
                    total_jobs += len(sky_jobs)
            except Exception as e:
                logger.warning(f"[Skywalker] fetch error: {e}")
            last_run["skywalker"] = now

    logger.info(f"[Worker] run_pipeline finished, total new jobs sent: {total_jobs}")


async def main_loop():
    while True:
        await run_pipeline()
        await asyncio.sleep(30)


if __name__ == "__main__":
    logger.info("🚀 Starting unified worker (Freelancer + PPH + Skywalker)")
    asyncio.run(main_loop())
