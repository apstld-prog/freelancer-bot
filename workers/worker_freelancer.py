import asyncio
import logging
import httpx
from datetime import datetime, timezone

from db import get_session
from db_keywords import get_keywords
from db_events import record_event, has_been_sent

logger = logging.getLogger("worker.freelancer")


API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"


async def fetch_jobs_for_keywords(keywords):
    async with httpx.AsyncClient(timeout=15) as client:
        query = ",".join(keywords)
        params = {
            "full_description": "false",
            "job_details": "false",
            "limit": 30,
            "offset": 0,
            "sort_field": "time_submitted",
            "sort_direction": "desc",
            "query": query
        }
        r = await client.get(API_URL, params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("result", {}).get("projects", [])


async def worker_loop():
    logger.info("🚀 Starting freelancer worker...")

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
                    desc = job.get("preview_description", "")

                    if not job_id:
                        continue

                    # Avoid duplicates
                    if has_been_sent(uid, "freelancer", job_id):
                        continue

                    # ✅ Record job in feed_event
                    record_event(
                        user_id=uid,
                        platform="freelancer",
                        external_id=str(job_id),
                        title=title,
                        description=desc,
                        affiliate_url=None,
                        original_url=f"https://www.freelancer.com/projects/{job_id}"
                    )

        except Exception as e:
            logger.error(f"Error in worker loop: {e}")

        # ---------------------------------------------
        # Worker sleep interval
        # ---------------------------------------------
        await asyncio.sleep(40)


def start():
    asyncio.run(worker_loop())

