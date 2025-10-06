# worker.py
import asyncio
import httpx
import logging
import os
import time

from db import get_session, User
from feedstats import write_stats
from feeds_config import FEEDS, AFFILIATE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
log = logging.getLogger("worker")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TG_SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Fallback keywords in case a user has none (you can remove if your DB has per-user keywords)
DEFAULT_KEYWORDS = ["logo", "led", "lighting", "φωτισμός"]

async def tg_send(chat_id: int, text: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(TG_SEND_URL, json={"chat_id": chat_id, "text": text})
        r.raise_for_status()

async def fetch_feed(client: httpx.AsyncClient, feed: str, keyword: str) -> dict:
    """Return {count, error} for a single feed/keyword probe (lightweight HEAD/GET)."""
    url = None
    if feed == "freelancer":
        url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?query={keyword}&limit=5&compact=true"
    elif feed == "peopleperhour":
        url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
    elif feed == "kariera":
        url = f"https://www.kariera.gr/jobs?keyword={keyword}"
    elif feed == "jobfind":
        url = f"https://www.jobfind.gr/ergasia?keyword={keyword}"

    if not url:
        return {"count": 0, "error": f"unknown feed {feed}"}

    try:
        r = await client.get(url)
        r.raise_for_status()
        # We don't parse full jobs here, this is just a health/count signal.
        # Use response length as a proxy "count" to keep it cheap.
        return {"count": len(r.text), "error": None}
    except Exception as e:
        return {"count": 0, "error": str(e)}

async def worker_loop():
    # DB session
    session_gen = get_session()
    db = next(session_gen)

    users = db.query(User).all()

    cycle_start = time.time()
    # Aggregate per-feed over the whole cycle
    feeds_totals = {f: {"count": 0, "error": None, "affiliate": bool(AFFILIATE.get(f, False))}
                    for f in FEEDS}
    sent_this_cycle = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for u in users:
            # If your model has per-user keywords, replace with u.keywords list.
            keywords = DEFAULT_KEYWORDS

            for kw in keywords:
                # Probe all feeds for this keyword
                feed_results = {}
                for f in FEEDS:
                    res = await fetch_feed(client, f, kw)
                    feed_results[f] = res

                    # aggregate
                    feeds_totals[f]["count"] += res.get("count", 0)
                    if res.get("error"):
                        feeds_totals[f]["error"] = res["error"]

                # Optional: let user know a probe ran (you can remove if noisy)
                try:
                    await tg_send(int(u.telegram_id), f"🔎 Checked '{kw}' across {len(FEEDS)} feeds.")
                    sent_this_cycle += 1
                except Exception as e:
                    log.warning(f"Send failed to {u.telegram_id}: {e}")

    cycle_seconds = int(time.time() - cycle_start)
    write_stats({
        "cycle_seconds": cycle_seconds,
        "sent_this_cycle": sent_this_cycle,
        "feeds": feeds_totals,  # includes affiliate flags
    })

    log.info(f"Worker cycle complete. Sent {sent_this_cycle} messages.")
    log.info(f"Feeds summary: {feeds_totals}")

if __name__ == "__main__":
    asyncio.run(worker_loop())
