# worker_runner.py
import time, logging
from worker import run_pipeline
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

INTERVAL = 120  # seconds

if __name__ == "__main__":
    logger.info("🚀 Worker started (every %ss)", INTERVAL)
    while True:
        try:
            items = run_pipeline([])
            logger.info("[runner] sent %s messages", len(items))
        except Exception as e:
            logger.exception("[runner] pipeline/send error: %s", e)
        time.sleep(INTERVAL)
