import os
import asyncio
import logging
from utils import fetch_json, get_all_active_users, send_job_to_user
from db_events import ensure_feed_events_schema, save_feed_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_freelancer")

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

def _collect_keywords(users):
    return ",".join(sorted({kw["keyword"] for u in users for kw in u.get("keywords", []) if kw.get("keyword")}))

async def process_once():
    ensure_feed_events_schema()

    users = get_all_active_users()
    if not users:
        logger.info("[Freelancer] No active users.")
        return

    keywords = _collect_keywords(users)
    if not keywords:
        logger.info("[Freelancer] No keywords for users.")
        return

    params = {
        "limit": 30,
        "sort_field": "time_submitted",
        "sort_direction": "desc",
        "full_description": "false",
        "query": keywords,
    }
    data = await fetch_json(API_URL, params)
    projects = data.get("result", {}).get("projects", [])
    logger.info(f"[Freelancer] fetched {len(projects)} jobs")

    for p in projects:
        job = {
            "id": p.get("id"),
            "title": p.get("title") or "",
            "description": p.get("preview_description") or "",
            "requirements": "",
            "platform": "Freelancer",
            "original_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "affiliate_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "budget_amount": (p.get("budget") or {}).get("minimum"),
            "budget_currency": (p.get("currency") or {}).get("code") or "USD",
            "created_at": p.get("time_submitted"),
            "matched_keyword": "",  # (προαιρετικά μπορείς να βάλεις match)
        }
        save_feed_event("freelancer", job["title"], job["description"], job["original_url"], job["budget_amount"], job["budget_currency"])

        for u in users:
            tid = u.get("telegram_id")
            if not tid:
                continue
            try:
                await send_job_to_user(None, int(tid), job)
            except Exception as e:
                logger.warning(f"[Freelancer] send failed to {tid}: {e}")

async def main():
    interval = int(os.getenv("WORKER_INTERVAL", 180))
    while True:
        try:
            await process_once()
        except Exception as e:
            logger.error(f"[Freelancer] loop error: {e}", exc_info=True)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
