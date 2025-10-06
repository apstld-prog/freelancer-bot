# worker.py
import asyncio
import httpx
import logging
import os
import time
from db import get_session, User, Job
from feedstats import write_stats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("db")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

FEEDS = [
    "freelancer",
    "peopleperhour",
    "kariera",
    "jobfind",
]

async def tg_send(chat_id, text):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(API_URL, json={"chat_id": chat_id, "text": text})
        r.raise_for_status()

async def fetch_jobs(keyword):
    results = {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for feed in FEEDS:
                url = ""
                if feed == "freelancer":
                    url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?query={keyword}&limit=5"
                elif feed == "peopleperhour":
                    url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
                elif feed == "kariera":
                    url = f"https://www.kariera.gr/jobs?keyword={keyword}"
                elif feed == "jobfind":
                    url = f"https://www.jobfind.gr/ergasia?keyword={keyword}"

                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    count = len(r.text)
                    results[feed] = {"count": count, "error": None}
                except Exception as e:
                    results[feed] = {"count": 0, "error": str(e)}
    except Exception as e:
        log.error(f"Error fetching jobs: {e}")
    return results

async def worker_loop():
    cycle_start = time.time()
    stats = {"feeds": {}}
    keywords = ["logo", "led", "lighting"]
    db = next(get_session())

    users = db.query(User).all()
    for u in users:
        for kw in keywords:
            feed_results = await fetch_jobs(kw)
            stats["feeds"].update(feed_results)

    stats["cycle_seconds"] = int(time.time() - cycle_start)
    write_stats(stats)
    log.info("Worker cycle complete. Sent messages and updated feed stats.")

if __name__ == "__main__":
    asyncio.run(worker_loop())
