import psycopg2
import os

DDL = """
CREATE TABLE IF NOT EXISTS feed_events (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    platform TEXT,
    title TEXT,
    description TEXT,
    budget TEXT,
    keyword TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def ensure_feed_events_schema():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    cur.close()
    conn.close()
