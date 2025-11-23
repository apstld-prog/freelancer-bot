# worker.py — FULL

import asyncio
import logging
import time
from datetime import datetime

from db_keywords import get_all_keywords
from platform_freelancer import get_items as fl_get_items
from platform_peopleperhour import get_items as pph_get_items
from platform_skywalker import get_items as sw_get_items

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

FETCH_INTERVAL = 180  # seconds

async def fetch_platform_items(keyword_list):
    """
    Fetch items from all enabled platforms.
    """
    items = []

    # Freelancer
    try:
        fl = fl_get_items(keyword_list)
        items.extend(fl)
    except Exception as e:
        log.warning(f"Freelancer error: {e}")

    # PeoplePerHour
    try:
        pph = pph_get_items(keyword_list)
        items.extend(pph)
    except Exception as e:
        log.warning(f"PPH error: {e}")

    # Skywalker
    try:
        sw = sw_get_items(keyword_list)
        items.extend(sw)
    except Exception as e:
        log.warning(f"Skywalker error: {e}")

    return items

async def worker_loop():
    log.info("Unified Worker loop starting...")
    while True:
        try:
            # 🔥 Read ALL keywords from DB
            keyword_rows = get_all_keywords()
            keyword_list = [k.keyword for k in keyword_rows]

            log.info(f"Loaded {len(keyword_list)} keywords")

            if keyword_list:
                items = await fetch_platform_items(keyword_list)
                log.info(f"Fetched total {len(items)} items")
            else:
                log.info("No keywords found")

        except Exception as e:
            log.error(f"Worker loop error: {e}")

        await asyncio.sleep(FETCH_INTERVAL)

def main():
    log.info("Unified Worker started")
    asyncio.run(worker_loop())

if __name__ == "__main__":
    main()
