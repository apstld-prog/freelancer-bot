import os
import psycopg2
from psycopg2.extras import DictCursor
import logging

logger = logging.getLogger("db")

# ------------------------------------------------------
# Database connection
# ------------------------------------------------------
def get_db_connection():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=DictCursor)
    return conn

# ------------------------------------------------------
# Ensure schema
# ------------------------------------------------------
def ensure_schema():
    """Ensure all required tables exist in the database."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            keywords TEXT,
            active BOOLEAN DEFAULT TRUE
        );
        """)
        conn.commit()
    conn.close()
    logger.info("✅ Database schema verified successfully")

# ------------------------------------------------------
# Compatibility layer for older imports
# ------------------------------------------------------
def get_session():
    """Compatibility alias for older SQLAlchemy-style code."""
    return get_db_connection()

def get_or_create_user_by_tid(tid):
    """Ensure user exists in user_settings and return their record."""
    ensure_schema()
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM user_settings WHERE user_id = %s;", (tid,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO user_settings (user_id, keywords, active) VALUES (%s, '', TRUE) RETURNING *;",
                (tid,),
            )
            conn.commit()
            cur.execute("SELECT * FROM user_settings WHERE user_id = %s;", (tid,))
            row = cur.fetchone()
    conn.close()
    return row

# ------------------------------------------------------
# Active user list for worker
# ------------------------------------------------------
def get_user_list():
    """Return list of active users and their keywords."""
    ensure_schema()
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT user_id, keywords FROM user_settings WHERE active = TRUE;")
        rows = cur.fetchall()
    conn.close()
    users = []
    for row in rows:
        uid = row["user_id"]
        kws = [k.strip() for k in (row["keywords"] or "").split(",") if k.strip()]
        if kws:
            users.append((uid, kws))
    logger.info(f"📋 Loaded {len(users)} active users from database")
    return users
