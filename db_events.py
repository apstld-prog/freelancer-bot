from sqlalchemy import text
from db import get_session

def ensure_schema():
    with get_session() as s:
        s.execute(text("""
        CREATE TABLE IF NOT EXISTS feed_events (
            id SERIAL PRIMARY KEY,
            platform TEXT,
            event_type TEXT,
            created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')
        );
        """))
        s.commit()

def log_platform_event(platform: str, event_type: str):
    with get_session() as s:
        s.execute(
            text("INSERT INTO feed_events (platform, event_type) VALUES (:p, :e)"),
            {"p": platform, "e": event_type}
        )
        s.commit()
