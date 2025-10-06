# worker_stats_sidecar.py
from __future__ import annotations
from typing import Dict, Any

# We import lazily to avoid circular issues if bot module isn’t present at import time
def publish_stats(*, feeds_counts: Dict[str, Any], cycle_seconds: float, sent_this_cycle: int) -> None:
    """
    Call this from the _end_ of each worker cycle, e.g.:

      from worker_stats_sidecar import publish_stats
      publish_stats(
          feeds_counts=feeds_totals_dict,  # {"freelancer":{"count":12,"error":None}, ...}
          cycle_seconds=cycle_duration_seconds,
          sent_this_cycle=sent_this_cycle,
      )
    """
    try:
        from feedsstatus_handler import _ingest  # type: ignore
        _ingest({
            "feeds_counts": feeds_counts,
            "cycle_seconds": cycle_seconds,
            "sent_this_cycle": sent_this_cycle,
        })
    except Exception:
        # Sidecar is best-effort; never break the worker
        pass
