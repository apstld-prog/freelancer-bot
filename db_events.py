import logging
from sqlalchemy import text
from db import get_session

log = logging.getLogger("db_events")

# ======================================================
#  Βοηθητικές συναρτήσεις για feed events & jobs
# ======================================================

def ensure_schema():
    """Ελέγχει/δημιουργεί τον πίνακα feed_events αν δεν υπάρχει."""
    try:
        with get_session() as s:
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS feed_events (
                    id SERIAL PRIMARY KEY,
                    platform TEXT,
                    created_at TIMESTAMP DEFAULT NOW() AT TIME ZONE 'UTC'
                )
            """))
            s.commit()
            log.info("✅ Table feed_events ensured")
    except Exception as e:
        log.warning("Failed to ensure schema: %s", e)


def log_platform_event(platform: str):
    """Καταγράφει ένα γεγονός feed/selftest για συγκεκριμένη πλατφόρμα."""
    try:
        ensure_schema()
        with get_session() as s:
            s.execute(
                text("""
                    INSERT INTO feed_events (platform, created_at)
                    VALUES (:p, NOW() AT TIME ZONE 'UTC')
                """),
                {"p": platform}
            )
            s.commit()
        log.info("feed_events row recorded for '%s'", platform)
    except Exception as e:
        log.warning("Failed to log platform event: %s", e)


def get_recent_event_count(hours: int = 24):
    """Επιστρέφει πόσα feed events υπήρξαν τις τελευταίες X ώρες."""
    try:
        with get_session() as s:
            rows = s.execute(
                text("""
                    SELECT COUNT(*) 
                    FROM feed_events 
                    WHERE created_at > (NOW() AT TIME ZONE 'UTC') - INTERVAL :h || ' hours'
                """),
                {"h": hours}
            ).scalar()
        return rows or 0
    except Exception as e:
        log.warning("Failed to count feed events: %s", e)
        return 0


def cleanup_old_events(days: int = 30):
    """Διαγράφει πολύ παλιά γεγονότα για καθαριότητα."""
    try:
        with get_session() as s:
            s.execute(
                text("""
                    DELETE FROM feed_events 
                    WHERE created_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL :d || ' days'
                """),
                {"d": days}
            )
            s.commit()
        log.info("🧹 Old feed_events older than %d days deleted", days)
    except Exception as e:
        log.warning("Failed to cleanup old feed events: %s", e)
