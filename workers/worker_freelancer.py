import os
import sys
import asyncio
import logging

# --- CRITICAL FIX ---
# Add project root so imports work even when script runs from /workers/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from platform_freelancer import fetch_freelancer_jobs
from utils import send_job_to_user, convert_to_usd, time_ago
from db import get_user_keywords
from db_events import record_fetched_jobs

logger = logging.getLogger("worker_freelancer")

async def process_freelancer_jobs():
    logger.info("[Freelancer Worker] Started")
    while True:
        try:
            user_keywords = get_user_keywords()
            for user_id, keywords in user_keywords.items():
                if not keywords:
                    continue

                jobs = fetch_freelancer_jobs(keywords)
                logger.info("[Freelancer] %d jobs fetched for %s", len(jobs), user_id)
                record_fetched_jobs("Freelancer", jobs)

                for job in jobs:
                    title = job.get("title", "")
                    desc = job.get("description", "")
                    matched_kw = next((k for k in keywords if k.lower() in (title + desc).lower()), None)
                    if not matched_kw:
                        continue

                    budget = job.get("budget", "N/A")
                    currency = job.get("currency", "")
                    usd_value = convert_to_usd(budget, currency)
                    posted_ago = time_ago(job.get("created_at"))

                    message = (
                        f"{title}\n"
                        f"💰 Budget: {budget} {currency} (~${usd_value} USD)\n"
                        f"🌐 Source: Freelancer\n"
                        f"🔍 Match: {matched_kw}\n"
                        f"📝 {desc}\n\n"
                        f"🕒 Posted: {posted_ago}"
                    )
                    await send_job_to_user(None, user_id, message, job)
            await asyncio.sleep(60)
        except Exception as e:
            logger.exception("[Freelancer Worker] Error: %s", e)
            await asyncio.sleep(120)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(process_freelancer_jobs())
