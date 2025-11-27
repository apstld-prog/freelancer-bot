from __future__ import annotations
import json, os, time
from typing import Any, Dict, Optional

STATS_PATH = os.getenv("WORKER_STATS_PATH", "/tmp/worker_stats.json")

_last_counts = {}

def incr(feed: str, count: int):
    global _last_counts
    row = _last_counts.setdefault(feed, {"count": 0, "error": None})
    row["count"] += count

def error(feed: str, err: str):
    global _last_counts
    _last_counts[feed] = {"count": 0, "error": err}

def publish_stats(*, cycle_seconds: float, sent_this_cycle: int) -> None:
    payload = {
        "ts": time.time(),
        "cycle_seconds": float(cycle_seconds),
        "sent_this_cycle": int(sent_this_cycle),
        "feeds_counts": _last_counts,
    }
    try:
        os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        import logging
        logging.getLogger("db").warning("publish_stats: failed to write %s", STATS_PATH)
