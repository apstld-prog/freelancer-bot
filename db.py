import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

class PsycopgSession:
    """Wrapper for psycopg2 connection with context manager support"""
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        self.cur = self.conn.cursor()

    def execute(self, query, params=None):
        self.cur.execute(query, params or {})
        return self.cur

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.cur.close()
        self.conn.close()

    # Context manager support
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.close()

def get_session():
    """Returns a new database session"""
    return PsycopgSession()

def ensure_schema():
    """Placeholder for schema creation if needed"""
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            username TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)
        s.commit()
