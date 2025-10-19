import os
import time
import importlib
import logging
from datetime import datetime, timedelta
from httpx import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("worker")

SEND_ENDPOINT = os.getenv("SEND_ENDPOINT", "http://localhost:10000/api/send_job")
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))  # default 2 λεπτά
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "48"))
FRESH_SINCE = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)

platforms = {
    "freelancer": "platform_freelancer",
    "peopleperhour": "platform_peopleperhour",
}

client = Client(timeout=15.0)


def send_to_bot(source: str, job: dict):
    try:
        resp = client.post(SEND_ENDPOINT, json={**job, "source": source})
        if resp.status_code != 200:
            log.warning(f"[SEND_FAIL] {source}: {resp.text}")
    except Exception as e:
        log.error(f"[SEND_ERR] {source}: {e}")


def process_platform(name: str, modname: str):
    try:
        mod = importlib.import_module(modname)
        log.debug(f"using {modname}.get_items()")
        items = mod.get_items(limit=50, fresh_since=FRESH_SINCE, logger=log)

        if not items:
            log.warning(f"[{name.upper()}] No results fetched.")
            return 0

        # Debug preview (first 3)
        for i, job in enumerate(items[:3]):
            title = job.get("title")
            desc = job.get("description", "")[:100].replace("\n", " ")
            budget = job.get("budget_usd") or job.get("budget_amount")
            log.info(f"[{name.upper()} PREVIEW] {i+1}. {title} | {budget} USD | {desc}")

        for job in items:
            send_to_bot(name, job)

        log.info(f"[{name.upper()}] ✅ sent {len(items)} jobs to bot")
        return len(items)
    except Exception as e:
        log.exception(f"[{name.upper()}] fetch/send error: {e}")
        return 0


def main():
    log.info("======================================================")
    log.info("🚀 Worker started — fetching jobs every %s sec", WORKER_INTERVAL)
    log.info("======================================================")

    while True:
        total = {}
        for name, modname in platforms.items():
            count = process_platform(name, modname)
            total[name] = count

        log.info(f"Worker summary: " + ", ".join([f"{k}={v}" for k, v in total.items()]))
        time.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("Worker interrupted by user.")
    except Exception as e:
        log.exception(f"Fatal worker error: {e}")
