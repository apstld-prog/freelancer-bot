# worker.py — Unified Worker, PPH SAFE MODE, 10 pages per keyword, dedupe

import asyncio
import time
import logging
from typing import List, Dict

import platform_freelancer as pf
import platform_peopleperhour as pph
import platform_skywalker as sky
import platform_careerjet as cj

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

ASYNC_INTERVAL = 60  # worker loop

async def fetch_all(keywords: List[str]) -> List[Dict]:
    all_results=[]

    # FREELANCER
    try:
        fr = pf.get_items(keywords)
        all_results.extend(fr)
    except Exception as e:
        log.warning(f"Freelancer failed: {e}")

    # PPH SAFE MODE (proxy)
    try:
        pph_items = pph.get_items(keywords)
        all_results.extend(pph_items)
    except Exception as e:
        log.warning(f"platform_peopleperhour failed: {e}")

    # SKYWALKER
    try:
        sk = sky.get_items(keywords)
        all_results.extend(sk)
    except Exception as e:
        log.warning(f"Skywalker failed: {e}")

    # CAREERJET
    try:
        cj_items = cj.get_items(keywords)
        all_results.extend(cj_items)
    except Exception as e:
        log.warning(f"Careerjet failed: {e}")

    return all_results

async def worker_loop():
    from db_keywords import get_all_keywords
    from job_logic import handle_new_jobs

    while True:
        keywords = get_all_keywords()
        kw_list = [k.keyword for k in keywords]

        if not kw_list:
            log.info("No keywords, sleeping...")
            await asyncio.sleep(20)
            continue

        log.info(f"Fetching for keywords: {kw_list}")

        items = await fetch_all(kw_list)

        log.info(f"Fetched total items: {len(items)}")

        # Dedup logic happens inside handle_new_jobs
        try:
            handle_new_jobs(items)
        except Exception as e:
            log.error(f"Handler failed: {e}")

        await asyncio.sleep(ASYNC_INTERVAL)

def main():
    log.info("Unified Worker started")
    asyncio.run(worker_loop())

if __name__ == "__main__":
    main()
