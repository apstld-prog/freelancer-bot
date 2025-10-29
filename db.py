import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


class PsycopgSession:
    """Wrapper for psycopg2 with context manager support."""
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        self.cur = self.conn.cursor()

    def execute(self, query, params=None):
        self.cur.execute(query, params or ())
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
    """Return new DB session"""
    return PsycopgSession()


def ensure_schema():
    """Ensures base user table exists"""
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            is_blocked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)
        s.commit()


def get_or_create_user_by_tid(telegram_id):
    """Ensures a user exists in the database and returns it"""
    with get_session() as s:
        s.execute("SELECT * FROM user WHERE telegram_id=%s;", (telegram_id,))
        user = s.fetchone()
        if not user:
            s.execute(
                "INSERT INTO user (telegram_id, username, is_admin, is_active, created_at, updated_at) "
                "VALUES (%s, %s, FALSE, TRUE, NOW(), NOW()) RETURNING *;",
                (telegram_id, f"user_{telegram_id}")
            )
            user = s.fetchone()
        s.commit()
        return user
