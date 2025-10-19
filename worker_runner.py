
# worker_runner.py — fixed try/except + per-platform intervals
import os, time, logging, importlib, traceback
from datetime import datetime, timezone, timedelta

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

# Intervals
DEFAULT_INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL)))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL_SECONDS", "600"))  # 10 minutes default

ENABLE_FREELANCER = os.getenv("ENABLE_FREELANCER", "1") == "1"
ENABLE_PPH = os.getenv("ENABLE_PPH", "1") == "1"

FRESH_WINDOW_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
MAX_PER_TICK = int(os.getenv("MAX_ITEMS_PER_TICK", "30"))
KEYWORDS = [k.strip() for k in os.getenv("KEYWORDS", "logo,led,lighting").split(",") if k.strip()]

def _load(name):
    try:
        return importlib.import_module(name)
    except Exception:
        log.exception("Failed to import %s", name)
        return None

freel = _load("platform_freelancer")
pph = _load("platform_peopleperhour")

last_run = {"freelancer": 0.0, "peopleperhour": 0.0}

def _due(which: str, now: float) -> bool:
    if which == "freelancer":
        return now - last_run[which] >= FREELANCER_INTERVAL
    if which == "peopleperhour":
        return now - last_run[which] >= PPH_INTERVAL
    return True

def _safe_get(mod, keywords, fresh_since, limit, source_name):
    if not mod:
        return []
    try:
        # prefer keyword arguments to tolerate different signatures
        return mod.get_items(keywords=keywords, fresh_since=fresh_since, limit=limit, logger=log)  # type: ignore
    except TypeError:
        try:
            return mod.get_items(keywords, fresh_since, limit)  # type: ignore
        except TypeError:
            try:
                return mod.get_items()  # last resort
            except Exception:
                log.exception("%s.get_items() failed", source_name)
                return []
    except Exception:
        log.exception("%s.get_items failed", source_name)
        return []

def run_once():
    now = time.time()
    since_dt = datetime.now(timezone.utc) - timedelta(hours=FRESH_WINDOW_HOURS)
    merged = []

    if ENABLE_FREELANCER and _due("freelancer", now):
        items = _safe_get(freel, KEYWORDS, since_dt, MAX_PER_TICK, "freelancer")
        for it in items:
            it.setdefault("source", "freelancer")
        last_run["freelancer"] = now
        log.info("freelancer fetched=%d", len(items))
        merged.extend(items)

    if ENABLE_PPH and _due("peopleperhour", now):
        items = _safe_get(pph, KEYWORDS, since_dt, MAX_PER_TICK, "peopleperhour")
        for it in items:
            it.setdefault("source", "peopleperhour")
        last_run["peopleperhour"] = now
        log.info("PPH fetched=%d", len(items))
        merged.extend(items)

    # Here you would forward 'merged' to your DB / bot pipeline.
    if merged:
        log.info("merged total=%d (last %d h)", len(merged), FRESH_WINDOW_HOURS)

def main():
    log.info("[Worker] Starting background process...")
    # Optional: selftest toggle block — FIXED with try/except/finally
    _orig_enable_pph = os.getenv("ENABLE_PPH", "1")
    try:
        if os.getenv("WORKER_SELFTEST_FORCE_PPH", "0") == "1":
            os.environ["ENABLE_PPH"] = "1"
    except Exception as e:
        log.warning("PPH toggle block failed: %s", e)
    finally:
        # restore on exit of main
        os.environ["ENABLE_PPH"] = _orig_enable_pph

    while True:
        try:
            run_once()
        except Exception:
            log.error("tick crashed:\n%s", traceback.format_exc())
        time.sleep( min(FREELANCER_INTERVAL, PPH_INTERVAL) )

if __name__ == "__main__":
    main()
