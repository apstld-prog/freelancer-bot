from db import get_session
from sqlalchemy import text

def log_platform_event(platform, count):
    with get_session() as s:
        s.execute(
            text("INSERT INTO feed_events (platform, event_count, created_at) "
                 "VALUES (:p, :c, NOW() AT TIME ZONE 'UTC')"),
            {"p": platform, "c": count}
        )
        s.commit()
