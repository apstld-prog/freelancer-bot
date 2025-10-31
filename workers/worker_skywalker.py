import os
import asyncio
import logging
from bs4 import BeautifulSoup
from utils import fetch_html, get_all_active_users, send_job_to_user
from db_events import ensure_feed_events_schema, save_feed_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_skywalker")

URL = "https://www.skywalker.gr/elGR/aggelies"

async def process_once():
    ensure_feed_events_schema()
    users = get_all_active_users()
    if not users:
        logger.info("[Skywalker] No active users.")
        return

    # collect keywords list
    keywords = [kw["keyword"] for u in users for kw in u.get("keywords", []) if kw.get("keyword")]
    if not keywords:
        logger.info("[Skywalker] No keywords.")
        return

    html = await fetch_html(URL)
    if not html:
        logger.info("[Skywalker] Empty HTML.")
        return

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="jobcard")
    logger.info(f"[Skywalker] fetched {len(cards)} cards")

    for c in cards:
        a = c.find("a", class_="jobcard-title")
        if not a:
            continue
        title = a.get_text(strip=True)
        link = "https://www.skywalker.gr" + a.get("href", "")
        desc_div = c.find("div", class_="jobcard-desc")
        desc = desc_div.get_text(strip=True) if desc_div else ""

        # keyword filter
        if not any(k.lower() in (title + " " + desc).lower() for k in keywords):
            continue

        job = {
            "id": hash(link) & 0x7FFFFFFF,
            "title": title,
            "description": desc,
            "requirements": "",
            "platform": "Skywalker",
            "original_url": link,
            "affiliate_url": link,
            "budget_amount": None,
            "budget_currency": "USD",
            "created_at": None,
            "matched_keyword": "",
        }
        save_feed_event("skywalker", job["title"], job["description"], job["original_url"], job["budget_amount"], job["budget_currency"])

        for u in users:
            tid = u.get("telegram_id")
            if not tid:
                continue
            try:
                await send_job_to_user(None, int(tid), job)
            except Exception as e:
                logger.warning(f"[Skywalker] send failed to {tid}: {e}")

async def main():
    interval = int(os.getenv("WORKER_INTERVAL", 180))
    while True:
        try:
            await process_once()
        except Exception as e:
            logger.error(f"[Skywalker] loop error: {e}", exc_info=True)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
