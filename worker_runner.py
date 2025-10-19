import os
import time
import logging
from datetime import datetime, timedelta

import platform_freelancer
import platform_peopleperhour

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("worker")

def run_worker():
    keywords_env = os.getenv("KEYWORDS", "logo,lighting,led,design")
    keywords = [k.strip() for k in keywords_env.split(",") if k.strip()]
    lookback_hours = int(os.getenv("PPH_LOOKBACK_HOURS", "48"))

    log.info("Worker started | keywords=%s | lookback=%dh", keywords, lookback_hours)

    since_time = datetime.utcnow() - timedelta(hours=lookback_hours)
    total_results = {"freelancer": 0, "pph": 0}

    for kw in keywords:
        # FREELANCER
        try:
            jobs_f = platform_freelancer.fetch(keywords=kw, fresh_since=since_time)
            total_results["freelancer"] += len(jobs_f)
            if jobs_f:
                log.info(f"[Freelancer] keyword='{kw}' → {len(jobs_f)} results")
                for j in jobs_f:
                    log.info(f"   └─ {j.get('title')} | {j.get('budget_currency')} {j.get('budget_amount')}")
            else:
                log.warning(f"[Freelancer] keyword='{kw}' → no results")
        except Exception as e:
            log.error(f"[Freelancer] fetch failed for '{kw}': {e}")

        # PEOPLEPERHOUR
        try:
            jobs_p = platform_peopleperhour.get_items(keywords=kw, fresh_since=since_time)
            total_results["pph"] += len(jobs_p)
            if jobs_p:
                log.info(f"[PPH] keyword='{kw}' → {len(jobs_p)} results")
                for j in jobs_p:
                    log.info(f"   └─ {j.get('title')} | {j.get('budget_currency')} {j.get('budget_amount')}")
            else:
                log.warning(f"[PPH] keyword='{kw}' → no results")
        except Exception as e:
            log.error(f"[PPH] fetch failed for '{kw}': {e}")

    log.info(f"Worker summary: freelancer={total_results['freelancer']}, peopleperhour={total_results['pph']}")

    if total_results["freelancer"] == 0 and total_results["pph"] == 0:
        log.warning("⚠ No jobs found from any source. Check parsing or API.")

if __name__ == "__main__":
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    log.info(f"Starting main worker loop (interval={interval}s)...")
    while True:
        run_worker()
        time.sleep(interval)
