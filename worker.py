import asyncio
import logging
from db_keywords import get_all_keywords

# platforms
from platform_freelancer import get_items as fl_get
from platform_peopleperhour_proxy import get_items as pph_get
from platform_skywalker import get_items as sw_get

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

FETCH_INTERVAL = 180


async def fetch_all(keywords):
    items = []

    # freelancer
    try:
        fl = fl_get(keywords)
        if isinstance(fl, list):
            items.extend(fl)
    except Exception as e:
        log.warning(f"Freelancer error: {e}")

    # peopleperhour
    try:
        pph = pph_get(keywords)
        if isinstance(pph, list):
            items.extend(pph)
    except Exception as e:
        log.warning(f"PPH error: {e}")

    # skywalker
    try:
        sw = sw_get(keywords)
        if isinstance(sw, list):
            items.extend(sw)
    except Exception as e:
        log.warning(f"Skywalker error: {e}")

    return items


async def worker_loop():
    log.info("Unified Worker starting...")

    while True:
        try:
            rows = get_all_keywords()
            keywords = [r.keyword for r in rows]

            log.info(f"Loaded {len(keywords)} keywords")

            if keywords:
                items = await fetch_all(keywords)
                log.info(f"Fetched total {len(items)} items.")
            else:
                log.info("No keywords found.")
        except Exception as e:
            log.error(f"Worker loop error: {e}")

        await asyncio.sleep(FETCH_INTERVAL)


def main():
    log.info("Unified Worker started.")
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
