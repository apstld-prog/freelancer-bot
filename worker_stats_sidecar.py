from __future__ import annotations
import json, os, time
from typing import Any, Dict, Optional

STATS_PATH = os.getenv("WORKER_STATS_PATH", "/tmp/worker_stats.json")

_last_counts: Dict[str, Dict[str, Any]] = {}

def incr(feed: str, count: int):
    """Αυξάνει το counter για ένα feed (freelancer, skywalker, κλπ)."""
    row = _last_counts.setdefault(feed, {"count": 0, "error": None})
    row["count"] += int(count)

def error(feed: str, err: str):
    """Καταγράφει σφάλμα για ένα feed."""
    _last_counts[feed] = {"count": 0, "error": str(err)}

def publish_stats(*, cycle_seconds: float, sent_this_cycle: int) -> None:
    """Γράφει το τελευταίο snapshot stats σε JSON."""
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

def read_last_cycle_stats() -> Optional[Dict[str, Any]]:
    """Διαβάζει το τελευταίο worker_stats.json, ή None αν δεν υπάρχει."""
    try:
        if not os.path.exists(STATS_PATH):
            return None
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
