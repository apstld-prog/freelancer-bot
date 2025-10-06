# worker_stats_sidecar.py
from __future__ import annotations
from typing import Dict, Any
from feedstats import write_stats

def publish_stats(feeds_counts: Dict[str, Any], cycle_seconds: int, sent_this_cycle: int) -> None:
    """
    feeds_counts π.χ.:
    {
      "freelancer":     {"count": 18, "error": None},
      "peopleperhour":  {"count": 0,  "error": "HTTP 429"},
      "kariera":        {"count": 32, "error": None},
      ...
    }
    """
    write_stats({
        "cycle_seconds": int(cycle_seconds),
        "sent_this_cycle": int(sent_this_cycle),
        "feeds": feeds_counts,
    })
