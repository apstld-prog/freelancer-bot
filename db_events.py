# db_events.py
import logging
from sqlalchemy import text
from db import get_session, close_session

log = logging.getLogger("db_events")

def ensure_feed_events_schema():
    """
    Creates feed_event table if missing (safe on Render).
    """
    db = get_session()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS feed_event (
                id SERIAL PRIMARY KEY,
                platform VARCHAR(50),
                title TEXT,
                description TEXT,
                affiliate_url TEXT,
                original_url TEXT,
                budget_amount NUMERIC,
                budget_currency VARCHAR(10),
                budget_usd NUMERIC,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        db.commit()
        log.info("✅ feed_event table ensured.")
    except Exception as e:
        log.error(f"feed_event schema error: {e}")
    finally:
        close_session(db)

