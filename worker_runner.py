import asyncio
import logging
import os
import time
import httpx

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

# -----------------------------------------------------
# Logging setup
# -----------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

# -----------------------------------------------------
# Environment variables
# -----------------------------------------------------
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL = int(os.getenv("GREEK_INTERVAL", "300"))

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "5254014824"))

# -----------------------------------------------------
# Telegram direct send (no import from bot.py)
# -----------------------------------------------------
async def send_jobs_to_user(chat_id: int, jobs, platform: str):
    """Send job messages directly via Telegram API."""
    if not BOT_TOKEN:
        logger.warning("[Worker] Missing TELEGRAM_TOKEN — cannot send messages")
        return 0

    sent_count = 0
    async with httpx.AsyncClient() as client:
        for job in jobs:
            try:
                title = job.get("title", "Untitled job")
                url = job.get("affiliate_url") or job.get("original_url", "")
                budget = job.get("budget_usd") or job.get("budget_amount") or ""
                if budget:
                    msg = f"💼 <b>{title}</b>\nBudget: ${budget}\n🔗 <a href=\"{url}\">View job</a>\n\nSource: {platform}"
                else:
                    msg = f"💼 <b>{title}</b>\n🔗 <a href=\"{url}\">View job</a>\n\nSource: {platform}"

                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True},
                    timeout=15,
                )
                sent_count += 1
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning(f"[Worker] send_jobs_to_user error: {e}")

    return sent_count

# -----------------------------------------------------
# Safe fetch wrapper
# -----------------------------------------------------
async def safe_fetch(fetch_func, platform_name):
    try:
        start = time.time()
        jobs = await fetch_func()
        elapsed = round(time.time() - start, 2)
        logger.info(f"[{platform_name}] fetched {len(jobs)} jobs in {elapsed}s")
        return jobs
    except Exception as e:
        logger.warning(f"[{platform_name}] fetch error: {e}")
        return []

# -----------------------------------------------------
# Main unified pipeline
# -----------------------------------------------------
async def run_pipeline():
    logger.info("🚀 Starting unified worker (Freelancer + PPH + Greek feeds)")
    last_run = {"freelancer": 0, "pph": 0, "skywalker": 0}
    sent_total = 0

    while True:
        now = time.time()

        # ---------- FREELANCER ----------
        if now - last_run["freelancer"] >= FREELANCER_INTERVAL:
            freelancer_jobs = await safe_fetch(fetch_freelancer_jobs, "Freelancer")
            if freelancer_jobs:
                sent = await send_jobs_to_user(ADMIN_CHAT_ID, freelancer_jobs, "Freelancer")
                logger.info(f"[Freelancer] sent {sent} jobs → {ADMIN_CHAT_ID}")
                sent_total += sent
            last_run["freelancer"] = now

        # ---------- PEOPLEPERHOUR ----------
        if now - last_run["pph"] >= PPH_INTERVAL:
            pph_jobs = await safe_fetch(fetch_pph_jobs, "PPH")
            if pph_jobs:
                sent = await send_jobs_to_user(ADMIN_CHAT_ID, pph_jobs, "PPH")
                logger.info(f"[PPH] sent {sent} jobs → {ADMIN_CHAT_ID}")
                sent_total += sent
            last_run["pph"] = now

        # ---------- SKYWALKER ----------
        if now - last_run["skywalker"] >= GREEK_INTERVAL:
            sky_jobs = await safe_fetch(fetch_skywalker_jobs, "Skywalker")
            if sky_jobs:
                sent = await send_jobs_to_user(ADMIN_CHAT_ID, sky_jobs, "Skywalker")
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
    logger.info("🚀 Starting worker process...")
    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        logger.info("Worker manually stopped.")
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
