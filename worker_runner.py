#!/usr/bin/env python3
# worker_runner.py — minimal runner to keep the Worker alive
# Does NOT alter UI, texts, or database schema. It only:
# 1) Imports your existing `worker` module
# 2) Optionally runs the cleanup once on start (configurable)
# 3) Stays alive in a simple loop (interval via env WORKER_INTERVAL)

import os
import time
import logging

try:
    import worker as _worker
except Exception as e:
    raise RuntimeError(f"Failed to import worker module: {e}")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

def main():
    interval = int(os.getenv("WORKER_INTERVAL", "60"))
    cleanup_toggle = os.getenv("WORKER_CLEANUP_DAYS", None)
    cleanup_days = int(cleanup_toggle) if (cleanup_toggle not in (None, "", "false", "False")) else 0

    log.info("[Runner] starting (interval=%ss, cleanup_days=%s)", interval, cleanup_days if cleanup_days else "disabled")

    # Optional 1-time cleanup on start (only if cleanup_days > 0)
    if cleanup_days > 0:
        try:
            if hasattr(_worker, "_cleanup_old_sent_jobs"):
                _worker._cleanup_old_sent_jobs(cleanup_days)
                log.info("[Runner] cleanup executed on start (days=%s)", cleanup_days)
            else:
                log.info("[Runner] cleanup skipped: _cleanup_old_sent_jobs not present")
        except Exception as e:
            log.warning("[Runner] cleanup on start failed: %s", e)

    # Keep-alive loop (you can later add your send loop here if needed)
    while True:
        time.sleep(interval)

if __name__ == "__main__":
    main()
