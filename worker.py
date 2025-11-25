# worker.py
import asyncio
import logging
from typing import List, Dict

import platform_freelancer as f
import platform_peopleperhour_proxy as p
import platform_skywalker as s

from db_keywords import get_unique_keywords

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

async def fetch_all(keywords: List[str]) -> List[Dict]:
    out = []

    try:
        out += f.get_items(keywords)
    except Exception as e:
        log.warning(f"freelancer error: {e}")

    try:
        out += p.get_items(keywords)
    except Exception as e:
        log.warning(f"pph error: {e}")

    try:
        out += s.get_items(keywords)
    except Exception as e:
        log.warning(f"skywalker error: {e}")

    return out

async def worker_loop():
    while True:
        kws = get_unique_keywords()
        if kws:
            items = await fetch_all(kws)
            log.info(f"Fetched {len(items)} items")
        await asyncio.sleep(180)

def main():
    log.info("Unified worker started")
    asyncio.run(worker_loop())

if __name__ == "__main__":
    main()
