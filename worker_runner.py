import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

import httpx

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from bot import send_jobs_to_user  # ✅ FIX: εισαγωγή από bot.py

# -----------------------------------------------------
# Logging setup
# -----------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

# -----------------------------------------------------
# Load environment variables
# -----------------------------------------------------
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL = int(os.getenv("GREEK_INTERVAL", "300"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "5254014824"))

# -----------------------------------------------------
# Cache & timestamps
# -----------------------------------------------------
last_run = {
    "freelancer": 0,
    "pph": 0,
    "skywalker": 0,
}

# -----------------------------------------------------
# Safe fetch wrapper
# -----------------------------------------------------
async def safe_fetch(fetch_func, platform_name, *args, **kwargs):
    try:
        start = time.time()
        jobs = await fetch_func(*args, **kwargs)
        elapsed = round(time.time() - start, 2)
        logger.info(f"[{platform_name}] fetched {len(jobs)} jobs in {elapsed}s")
        return jobs
    except Exception as e:
        logger.warning(f"[{platform_name}] error: {e}")
        return []

# -----------------------------------------------------
# Main unified pipeline
# -----------------------------------------------------
async def run_pipeline():
    logger.info("🚀 Starting unified worker (Freelancer + PPH + Greek feeds)")
    sent_total = 0

    while True:
        now = time.time()

        # ---------- FREELANCER ----------
        if now - last_run["freelancer"] >= FREELANCER_INTERVAL:
            freelancer_jobs = await safe_fetch(fetch_freelancer_jobs, "Freelancer")
            if freelancer_jobs:
                sent = await send_jobs_to_user(ADMIN_CHAT_ID, freelancer_jobs, platform="Freelancer")
                logger.info(f"[Freelancer] sent {sent} jobs → {ADMIN_CHAT_ID}")
                sent_total += sent
            last_run["freelancer"] = now

        # ---------- PEOPLEPERHOUR ----------
        if now - last_run["pph"] >= PPH_INTERVAL:
            pph_jobs = await safe_fetch(fetch_pph_jobs, "PPH")
            if pph_jobs:
                sent = await send_jobs_to_user(ADMIN_CHAT_ID, pph_jobs, platform="PPH")
                logger.info(f"[PPH] sent {sent} jobs → {ADMIN_CHAT_ID}")
                sent_total += sent
            last_run["pph"] = now

        # ---------- SKYWALKER ----------
        if now - last_run["skywalker"] >= GREEK_INTERVAL:
            sky_jobs = await safe_fetch(fetch_skywalker_jobs, "Skywalker")
            if sky_jobs:
                sent = await send_jobs_to_user(ADMIN_CHAT_ID, sky_jobs, platform="Skywalker")
                logger.info(f"[Skywalker] sent {sent} jobs → {ADMIN_CHAT_ID}")
                sent_total += sent
            last_run["skywalker"] = now

        # ---------- Wait ----------
        await asyncio.sleep(5)
        logger.debug(f"[Worker] Loop tick, total sent so far = {sent_total}")

# -----------------------------------------------------
# Entrypoint
# -----------------------------------------------------
if __name__ == "__main__":
    logger.info("🚀 Starting safe worker runner...")
    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        logger.info("Worker manually stopped.")
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
