import os
import psycopg2
import logging

logger = logging.getLogger("db")
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    if not DB_URL:
        raise Exception("DATABASE_URL missing")
    return psycopg2.connect(DB_URL)

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
