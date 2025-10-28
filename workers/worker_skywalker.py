import asyncio
import logging
from platform_skywalker import fetch_skywalker_jobs
from utils import send_job_to_user, convert_to_usd, time_ago
from db import get_user_keywords
from db_events import record_fetched_jobs

logger = logging.getLogger("worker_skywalker")

async def process_skywalker_jobs(app):
    logger.info("[Skywalker Worker] Started")
    while True:
        try:
            user_keywords = await get_user_keywords()
            for user_id, keywords in user_keywords.items():
                if not keywords:
                    continue

                jobs = fetch_skywalker_jobs(keywords)
                logger.info("[Skywalker] %d jobs fetched for %s", len(jobs), user_id)

                # 🔸 Καταγραφή όλων των jobs στη βάση
                record_fetched_jobs("Skywalker", jobs)

                for job in jobs:
                    title = job.get("title", "")
                    desc = job.get("description", "")
                    matched_kw = next(
                        (k for k in keywords if k.lower() in (title + desc).lower()), None
                    )
                    if not matched_kw:
                        continue

                    budget = job.get("budget", "N/A")
                    currency = job.get("currency", "")
                    usd_value = convert_to_usd(budget, currency)
                    posted_ago = time_ago(job.get("created_at"))

                    message = (
                        f"{title}\n"
                        f"💰 Budget: {budget} {currency} (~${usd_value} USD)\n"
                        f"🌐 Source: Skywalker\n"
                        f"🔍 Match: {matched_kw}\n"
                        f"📝 {desc}\n\n"
                        f"🕒 Posted: {posted_ago}"
                    )
                    await send_job_to_user(app, user_id, message, job)
            await asyncio.sleep(300)
        except Exception as e:
            logger.exception("[Skywalker Worker] Error: %s", e)
            await asyncio.sleep(120)
