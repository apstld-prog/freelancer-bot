import logging
from sqlalchemy import text
from db import get_session

logger = logging.getLogger("db_events")


# ---------------------------------------------------------
# Ensure feed_event table exists
# ---------------------------------------------------------
def ensure_feed_events_schema():
    """
    Creates or updates the feed_event table needed by all workers.
    Automatically runs on startup for bot + workers.
    """
    db = get_session()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS feed_event (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                platform VARCHAR(50) NOT NULL,
                job_id VARCHAR(255) NOT NULL,
                keyword VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            );
        """))

        # Unique index prevents duplicates
        db.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_event
            ON feed_event (user_id, platform, job_id, keyword);
        """))

        db.commit()
        logger.info("✅ feed_event table ensured.")
    except Exception as e:
        db.rollback()
        logger.error(f"❌ feed_event migration error: {e}")
        raise
    finally:
        db.close()


# ---------------------------------------------------------
# Record an event from a worker
# ---------------------------------------------------------
def record_event(user_id: int, platform: str, job_id: str, keyword: str):
    """
    Inserts a new event into feed_event.
    Is called by ALL workers whenever a job is sent.
    Duplicate events are automatically skipped.
    """
    db = get_session()
    try:
        db.execute(text("""
            INSERT INTO feed_event (user_id, platform, job_id, keyword)
            VALUES (:u, :p, :j, :k)
            ON CONFLICT (user_id, platform, job_id, keyword)
            DO NOTHING;
        """), {"u": user_id, "p": platform, "j": job_id, "k": keyword})

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"❌ record_event failed: {e}")
    finally:
        db.close()


# ---------------------------------------------------------
# Get statistics for UI
# ---------------------------------------------------------
def get_platform_stats(user_id: int):
    """
    Returns a dict:
    {
        'freelancer': 12,
        'peopleperhour': 5,
        'skywalker': 3,
        ...
    }
    """
    db = get_session()
    try:
        result = db.execute(text("""
            SELECT platform, COUNT(*) 
            FROM feed_event
            WHERE user_id = :u
            GROUP BY platform
            ORDER BY platform ASC;
        """), {"u": user_id})

        data = {row[0]: row[1] for row in result}
        return data
    except Exception as e:
        logger.error(f"❌ get_platform_stats failed: {e}")
        return {}
    finally:
        db.close()

