import logging
from sqlalchemy import text
from db import get_session

log = logging.getLogger("db_events")


def ensure_feed_events_schema():
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS feed_event (
                id SERIAL PRIMARY KEY,
                platform TEXT,
                keyword_match TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        s.commit()
        log.info("âœ… feed_event table ensured.")


def get_platform_stats(hours=24):
    with get_session() as s:
        rows = s.execute(
            text("""
                SELECT platform, COUNT(*) 
                FROM feed_event
                WHERE created_at >= NOW() - (INTERVAL '1 hour' * :h)
                GROUP BY platform
            """),
            {"h": hours}
        ).fetchall()

    stats = {r[0]: r[1] for r in rows}
    log.info(f"ðŸ“Š Platform stats (last {hours}h): {stats}")
    return stats

