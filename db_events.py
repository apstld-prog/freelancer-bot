import psycopg2
import os
import logging

logger = logging.getLogger("db_events")

DB_URL = os.getenv("DATABASE_URL")

def ensure_feed_events_schema():
    """Ensure that the feed_events table exists."""
    if not DB_URL:
        logger.error("[db_events] ❌ Missing DATABASE_URL environment variable")
        return

    ddl = """
    CREATE TABLE IF NOT EXISTS feed_events (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        platform VARCHAR(50) NOT NULL,
        title TEXT,
        url TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """

    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute(ddl)
            conn.commit()
        conn.close()
        logger.info("[db_events] ✅ Feed events schema verified successfully")
    except Exception as e:
        logger.error(f"[db_events] ❌ Error ensuring feed_events schema: {e}")
