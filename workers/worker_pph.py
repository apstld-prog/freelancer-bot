import os
import asyncio
import logging
from utils import fetch_json, get_all_active_users, send_job_to_user
from db_events import ensure_feed_events_schema, save_feed_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_pph")

API_URL = "https://www.peopleperhour.com/api/v1/projects"  # placeholder endpoint

def _collect_keywords(users):
    return ",".join(sorted({kw["keyword"] for u in users for kw in u.get("keywords", []) if kw.get("keyword")}))

async def process_once():
    ensure_feed_events_schema()
    users = get_all_active_users()
    if not users:
        logger.info("[PPH] No active users.")
        return

    keywords = _collect_keywords(users)
    if not keywords:
        logger.info("[PPH] No keywords.")
        return

    params = {"query": keywords, "page": 1}
    data = await fetch_json(API_URL, params)
    projects = data.get("projects", [])
    logger.info(f"[PPH] fetched {len(projects)} jobs")

    for p in projects:
        job_id = p.get("id")
        job = {
            "id": job_id,
            "title": p.get("title") or "",
            "description": p.get("description") or "",
            "requirements": "",
            "platform": "PeoplePerHour",
            "original_url": f"https://www.peopleperhour.com/job/{job_id}",
            "affiliate_url": f"https://www.peopleperhour.com/job/{job_id}",
            "budget_amount": (p.get("budget") or {}).get("amount"),
            "budget_currency": (p.get("budget") or {}).get("currency") or "USD",
            "created_at": p.get("created_at"),
            "matched_keyword": "",
        }
        save_feed_event("pph", job["title"], job["description"], job["original_url"], job["budget_amount"], job["budget_currency"])

        for u in users:
            tid = u.get("telegram_id")
            if not tid:
                continue
            try:
                await send_job_to_user(None, int(tid), job)
            except Exception as e:
                logger.warning(f"[PPH] send failed to {tid}: {e}")

async def main():
    interval = int(os.getenv("WORKER_INTERVAL", 180))
    while True:
        try:
            await process_once()
        except Exception as e:
            logger.error(f"[PPH] loop error: {e}", exc_info=True)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
