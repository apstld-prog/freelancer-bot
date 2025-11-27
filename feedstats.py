# feedstats.py
# Διαβάζει τα τελευταία stats από τον worker (worker_stats_sidecar).

from typing import Dict
from worker_stats_sidecar import read_last_cycle_stats

def get_feed_stats_last_24h() -> Dict[str, int]:
    """
    Επιστρέφει dict {source: count} από το τελευταίο worker_stats.json.
    Τα counts είναι τα raw items που γύρισαν τα feeds στον τελευταίο κύκλο.
    """
    data = read_last_cycle_stats()
    if not data:
        return {}

    feeds = data.get("feeds_counts") or {}
    out: Dict[str, int] = {}
    for name, row in feeds.items():
        try:
            out[name] = int(row.get("count", 0))
        except Exception:
            continue

    out["__total__"] = sum(v for k, v in out.items() if k != "__total__")
    return out
