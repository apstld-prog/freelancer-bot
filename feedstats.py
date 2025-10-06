# feedstats.py
from __future__ import annotations
import json, os, tempfile, time
from typing import Dict, Any

PATH = "/tmp/feedstats.json"

def write_stats(stats: Dict[str, Any]) -> None:
    """
    Παράδειγμα stats:
    {
        "cycle_seconds": 120,
        "feeds": {
            "freelancer": {"count": 12, "error": None},
            "peopleperhour": {"count": 0, "error": "HTTP 429"},
        }
    }
    """
    payload = {"generated_at": time.time(), **stats}
    os.makedirs(os.path.dirname(PATH) or "/", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="feedstats-", dir=os.path.dirname(PATH) or "/tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, PATH)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def read_stats() -> Dict[str, Any]:
    try:
        with open(PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"generated_at": 0, "feeds": {}, "cycle_seconds": None}
