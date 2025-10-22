import os
import time
import threading
import logging
from worker import run_pipeline
from utils_db import get_all_users
from telegram_send import send_jobs_to_user

# ===========================
# CONFIGURATION
# ===========================
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))  # default (3 min)
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL = int(os.getenv("GREEK_INTERVAL", "300"))

# ===========================
# LOGGING
# ===========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

logger.info(f"Worker initialized with intervals: "
            f"Freelancer={FREELANCER_INTERVAL}s, "
            f"PPH={PPH_INTERVAL}s, "
            f"Greek={GREEK_INTERVAL}s, "
            f"Default={WORKER_INTERVAL}s")

# ===========================
# TRACK LAST RUN PER PLATFORM
# ===========================
last_run = {
    "freelancer": 0,
    "pph": 0,
    "skywalker": 0,
    "kariera": 0,
    "careerjet": 0
}

# ===========================
# MAIN LOOP
# ===========================
def worker_loop():
    logger.info("✅ Worker loop started.")
    while True:
        try:
            users = get_all_users()
            now = time.time()

            for user in users:
                user_id = user["id"]
                keywords = user.get("keywords", [])
                logger.debug(f"tick user={user_id} kw={keywords}")

                # --- FREELANCER ---
                if now - last_run["freelancer"] >= FREELANCER_INTERVAL:
                    try:
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"Freelancer sent {len(jobs)} jobs to user={user_id}")
                        last_run["freelancer"] = now
                    except Exception as e:
                        logger.warning(f"Freelancer error: {e}")

                # --- PEOPLEPERHOUR ---
                if now - last_run["pph"] >= PPH_INTERVAL:
                    try:
                        os.environ["CURRENT_SOURCE"] = "peopleperhour"
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"PPH sent {len(jobs)} jobs to user={user_id}")
                        last_run["pph"] = now
                    except Exception as e:
                        logger.warning(f"PPH error: {e}")

                # --- SKYwalker + Greek feeds ---
                if now - last_run["skywalker"] >= GREEK_INTERVAL:
                    try:
                        os.environ["CURRENT_SOURCE"] = "skywalker"
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"Skywalker sent {len(jobs)} jobs to user={user_id}")
                        last_run["skywalker"] = now
                    except Exception as e:
                        logger.warning(f"Skywalker error: {e}")

                # --- Kariera ---
                if now - last_run["kariera"] >= GREEK_INTERVAL:
                    try:
                        os.environ["CURRENT_SOURCE"] = "kariera"
                        jobs = run_pipeline(keywords)
                        if jobs:
                            send_jobs_to_user(user_id, jobs)
                            logger.info(f"Kariera sent {len(jobs)} jobs to user={user_id}")
                        last_run["kariera"] = now
                    except Exception as e:
                        logger.warning(f"Kariera error: {e}")

            time.sleep(WORKER_INTERVAL)

        except Exception as e:
            logger.error(f"[runner compat] pipeline error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    logger.info("🚀 Starting multi-source worker (Freelancer + PPH + Greek feeds)")
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    t.join()
