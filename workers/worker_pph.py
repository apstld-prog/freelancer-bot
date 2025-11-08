import asyncio
import logging
import httpx
from datetime import datetime, timezone

from db import get_session
from db_keywords import get_keywords
from db_events import record_event, has_been_sent

logger = logging.getLogger("worker.pph")

API_URL = "https://www.peopleperhour.com/api/hourlies"


async def fetch_jobs_for_keywords(keywords):
    async with httpx.AsyncClient(timeout=15) as client:
        query = ",".join(keywords)
        params = {
            "search": query,
            "sort": "newest",
            "page": 1
        }
        r = await client.get(API_URL, params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("hourlies", [])


async def worker_loop():
    logger.info("🚀 Starting peopleperhour worker...")

    while True:
        try:
            session = get_session()

            # ---------------------------------------------
            # Fetch all users who have keywords
            # ---------------------------------------------
            rows = session.execute(
                "SELECT DISTINCT user_id FROM keyword"
            ).fetchall()
            user_ids = [r[0] for r in rows]

            session.close()

            # ---------------------------------------------
            # Run per-user
            # ---------------------------------------------
            for uid in user_ids:
                keywords = get_keywords(uid)
                if not keywords:
                    continue

                jobs = await fetch_jobs_for_keywords(keywords)

                # -----------------------------------------
                # Filter + Send events to db_events
                # -----------------------------------------
                for job in jobs:
                    job_id = job.get("id")
                    title = job.get("title", "")
                    desc = job.get("description", "")

                    if not job_id:
                        continue

                    # Avoid duplicates
                    if has_been_sent(uid, "pph", job_id):
                        continue

                    record_event(
                        user_id=uid,
                        platform="pph",
                        external_id=str(job_id),
                        title=title,
                        description=desc,
                        affiliate_url=None,
                        original_url=f"https://www.peopleperhour.com/hourlie/{job_id}"
                    )

        except Exception as e:
            logger.error(f"Error in worker loop: {e}")

        await asyncio.sleep(40)


def start():
    asyncio.run(worker_loop())

