import os
import psycopg2
from psycopg2.extras import DictCursor

def get_db_connection():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=DictCursor)
    return conn

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
    return users
