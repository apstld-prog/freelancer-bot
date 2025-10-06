# feedstats.py
# Read/Write last worker cycle stats for /feedsstatus

import json
import os
from typing import Dict, Any

STATS_PATH = os.environ.get("FEEDSTATS_PATH", "/tmp/feedstats.json")

def write_stats(stats: Dict[str, Any]) -> None:
    """
    stats = {
      "cycle_seconds": int,
      "sent_this_cycle": int,
      "feeds": {
        "<feed>": {"count": int, "error": str|None, "affiliate": bool}
      }
    }
    """
    tmp_path = STATS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATS_PATH)

def read_stats() -> Dict[str, Any]:
    if not os.path.exists(STATS_PATH):
        return {}
    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
