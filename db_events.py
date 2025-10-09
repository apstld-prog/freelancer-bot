# db_events.py — feed events schema + stats
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from sqlalchemy import text
from db import get_session

DDL = """
CREATE TABLE IF NOT EXISTS feed_events (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source VARCHAR(120) NOT NULL,
  payload JSONB
);
CREATE INDEX IF NOT EXISTS idx_feed_events_ts ON feed_events (ts);
CREATE INDEX IF NOT EXISTS idx_feed_events_source ON feed_events (source);
"""

def ensure_feed_events_schema() -> None:
    """Create feed_events table & indexes if they don't exist."""
    with get_session() as s:
        s.execute(text(DDL))
        s.commit()

def record_event(source: str, payload: Optional[dict] = None) -> None:
    """Optional helper to insert an event (call this όταν φτάνει job από πηγή)."""
    with get_session() as s:
        s.execute(
            text("INSERT INTO feed_events (source, payload) VALUES (:source, :payload)"),
            {"source": source, "payload": payload},
        )
        s.commit()

def get_platform_stats(window_hours: int = 24) -> Dict[str, int]:
    """Return counts per source for last `window_hours`."""
    with get_session() as s:
        q = text(
            "SELECT source, COUNT(*) FROM feed_events "
            "WHERE ts >= :ts_from GROUP BY source ORDER BY 2 DESC"
        )
        ts_from = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        rows = s.execute(q, {"ts_from": ts_from}).fetchall()
        return {r[0]: int(r[1]) for r in rows}
