import logging
from sqlalchemy import text
from db import get_session, close_session

log = logging.getLogger("db_events")


def ensure_feed_events_schema():
    db = get_session()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS feed_event (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                platform TEXT,
                job_id TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            );
        """))
        db.commit()
    finally:
        close_session(db)


def record_event(user_id: int, platform: str, job_id: str):
    db = get_session()
    try:
        db.execute(
            text("INSERT INTO feed_event (user_id, platform, job_id) VALUES (:u, :p, :j)"),
            {"u": user_id, "p": platform, "j": job_id}
        )
        db.commit()
    finally:
        close_session(db)


def get_platform_stats(hours: int = 24):
    db = get_session()
    try:
        rows = db.execute(text("""
            SELECT platform, COUNT(*) 
            FROM feed_event 
            WHERE sent_at > NOW() - (INTERVAL '1 hour' * :h)
            GROUP BY platform;
        """), {"h": hours}).fetchall()

        return {r[0]: r[1] for r in rows}
    finally:
        close_session(db)


