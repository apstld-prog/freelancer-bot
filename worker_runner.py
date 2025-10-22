import os
import time
import threading
import logging

try:
    from worker import run_pipeline
except Exception as e:
    print("Import error in worker:", e)
    run_pipeline = None

try:
    from utils_db import get_all_users
except Exception as e:
    print("Import error in utils_db:", e)
    get_all_users = lambda: []

try:
    from telegram_send import send_jobs_to_user
except Exception as e:
    print("Import error in telegram_send:", e)
    send_jobs_to_user = lambda uid, jobs: None

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL = int(os.getenv("GREEK_INTERVAL", "300"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

last_run = {"freelancer": 0, "pph": 0, "skywalker": 0, "kariera": 0}

def worker_loop():
    logger.info("✅ Worker loop started safely.")
    while True:
        try:
            users = get_all_users() or []
            now = time.time()

            for user in users:
                user_id = user.get("id") if isinstance(user, dict) else user
                keywords = user.get("keywords", []) if isinstance(user, dict) else []
                logger.debug(f"tick user={user_id} kw={keywords}")

                # --- FREELANCER ---
                if now - last_run["freelancer"] >= FREELANCER_INTERVAL and run_pipeline:
                    try:
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"Freelancer sent {len(jobs)} jobs to user={user_id}")
                        last_run["freelancer"] = now
                    except Exception as e:
                        logger.warning(f"Freelancer error: {e}")

                # --- PPH ---
                if now - last_run["pph"] >= PPH_INTERVAL and run_pipeline:
                    try:
                        os.environ["CURRENT_SOURCE"] = "peopleperhour"
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"PPH sent {len(jobs)} jobs to user={user_id}")
                        last_run["pph"] = now
                    except Exception as e:
                        logger.warning(f"PPH error: {e}")

                # --- SKYwalker ---
                if now - last_run["skywalker"] >= GREEK_INTERVAL and run_pipeline:
                    try:
                        os.environ["CURRENT_SOURCE"] = "skywalker"
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"Skywalker sent {len(jobs)} jobs to user={user_id}")
                        last_run["skywalker"] = now
                    except Exception as e:
                        logger.warning(f"Skywalker error: {e}")

            time.sleep(WORKER_INTERVAL)
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    logger.info("🚀 Starting safe worker runner...")
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    t.join()
