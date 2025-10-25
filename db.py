import os
import psycopg2
import logging

logger = logging.getLogger("db")
DB_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------
# Connection management
# ---------------------------------------------------

def get_connection():
    """Return a PostgreSQL connection."""
    if not DB_URL:
        raise Exception("DATABASE_URL missing")
    return psycopg2.connect(DB_URL)

# ---------------------------------------------------
# Schema management
# ---------------------------------------------------

def ensure_schema():
    """Ensure all required tables exist."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            keywords TEXT,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS saved_jobs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            platform VARCHAR(50),
            title TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS feed_events (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            platform VARCHAR(50),
            title TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
    ]
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            for ddl in ddl_statements:
                cur.execute(ddl)
            conn.commit()
        conn.close()
        logger.info("[DB] ✅ Schema verified successfully")
    except Exception as e:
        logger.error(f"[DB] ❌ Schema verification failed: {e}")

# ---------------------------------------------------
# User helpers
# ---------------------------------------------------

def get_user_list():
    """Return all active users with keywords."""
    users = []
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, keywords FROM user_settings WHERE active=TRUE;")
            users = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"[DB] Error loading users: {e}")
    return users

# ---------------------------------------------------
# Backward compatibility for bot.py
# ---------------------------------------------------

def get_session():
    """Return a psycopg2 connection (backward compatibility)."""
    return get_connection()

def get_or_create_user_by_tid(tid):
    """Ensure user exists safely in user_settings."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM user_settings WHERE user_id=%s;", (tid,))
            result = cur.fetchone()
            if not result:
                cur.execute("INSERT INTO user_settings (user_id, active) VALUES (%s, TRUE);", (tid,))
                conn.commit()
        conn.close()
        logger.info(f"[DB] ✅ User ensured for tid={tid}")
    except Exception as e:
        logger.error(f"[DB] get_or_create_user_by_tid error: {e}")
