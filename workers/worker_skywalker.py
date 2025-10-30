import asyncio
import logging
import os
from datetime import datetime, timezone
from db_events import ensure_feed_events_schema, save_feed_event
from utils import fetch_html, get_all_active_users, send_job_to_user
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_skywalker")

URL = "https://www.skywalker.gr/elGR/aggelies"

async def process_jobs():
    logger.info("[Skywalker Worker] Started")
    ensure_feed_events_schema()

    users = get_all_active_users()
    if not users:
        logger.warning("[Skywalker] No active users found.")
        return

    keywords = [
        kw["keyword"]
        for u in users
        for kw in u.get("keywords", [])
        if kw.get("keyword")
    ]
    if not keywords:
        logger.warning("[Skywalker] No keywords available.")
        return

    html = await fetch_html(URL)
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="jobcard")

    jobs = []
    for c in cards:
        title = c.find("a", class_="jobcard-title").get_text(strip=True)
        link = "https://www.skywalker.gr" + c.find("a", class_="jobcard-title")["href"]
        desc = c.find("div", class_="jobcard-desc").get_text(strip=True)
        jobs.append((title, desc, link))

    logger.info(f"[Skywalker] ✅ {len(jobs)} jobs fetched")

    for title, desc, link in jobs:
        for kw in keywords:
            if kw.lower() in title.lower() or kw.lower() in desc.lower():
                save_feed_event("skywalker", title, desc, link, None, None)
                message = f"💼 <b>{title}</b>\n🔗 {link}"

                for user in users:
                    tg_id = user.get("telegram_id")
                    if not tg_id:
                        logger.warning(f"[send_job_to_user] Skipping invalid user without telegram_id: {user}")
                        continue
                    try:
                        await send_job_to_user(None, int(tg_id), message, {"title": title})
                    except Exception as e:
                        logger.error(f"[Skywalker] Error sending to user {tg_id}: {e}")

async def main():
    while True:
        await process_jobs()
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", 120)))

if __name__ == "__main__":
    asyncio.run(main())
