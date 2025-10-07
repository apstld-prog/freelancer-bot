# worker_stats_sidecar.py
# Απλό “sidecar” για να ανταλλάσσει ο worker στατιστικά με το bot
# μέσω ενός JSON αρχείου στο filesystem.

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

# Πού θα σωζεται το αρχείο με τα στατιστικά
STATS_PATH = os.getenv("WORKER_STATS_PATH", "/tmp/worker_stats.json")


def publish_stats(
    *,
    feeds_counts: Dict[str, Dict[str, Any]],
    cycle_seconds: float,
    sent_this_cycle: int,
) -> None:
    """
    Καλείται από τον worker στο τέλος κάθε κύκλου.
    feeds_counts: π.χ. {"freelancer": {"count": 12, "error": None}, ...}
    """
    payload = {
        "ts": time.time(),
        "cycle_seconds": float(cycle_seconds),
        "sent_this_cycle": int(sent_this_cycle),
        "feeds_counts": feeds_counts or {},
    }
    try:
        # βεβαιώνουμε ότι υπάρχει ο φάκελος
        os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        # δεν σηκώνουμε εξαίρεση – απλώς αφήνουμε log στον worker
        import logging

        logging.getLogger("db").warning("publish_stats: failed to write %s", STATS_PATH)


def read_last_cycle_stats() -> Optional[Dict[str, Any]]:
    """
    Καλείται από το bot (/feedsstatus) για να διαβάσει το τελευταίο snapshot.
    Επιστρέφει dict ή None αν δεν υπάρχει τίποτα/σφάλμα.
    """
    try:
        if not os.path.exists(STATS_PATH):
            return None
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
