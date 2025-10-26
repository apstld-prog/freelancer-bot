import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime, timezone
from platform_freelancer import fetch_freelancer_jobs
from utils import send_job_to_user
from utils_fx import time_ago
from currency_usd import convert_to_usd
from db import get_user_keywords

logger = logging.getLogger("worker_freelancer")

async def process_freelancer_jobs(app):
    logger.info("[Freelancer Worker] Started")
    while True:
        try:
            user_keywords = await get_user_keywords()
            for user_id, keywords in user_keywords.items():
                if not keywords:
                    continue
                jobs = fetch_freelancer_jobs(keywords)
                logger.info(f"[Freelancer] {len(jobs)} jobs fetched for {user_id}")

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
                    await send_job_to_user(app, user_id, message, job)
            await asyncio.sleep(60)
        except Exception as e:
            logger.exception(f"[Freelancer Worker] Error: {e}")
            await asyncio.sleep(120)
