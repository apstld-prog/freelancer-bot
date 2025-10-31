# db.py — FINAL COMPATIBLE VERSION
# Compatible with bot.py expecting u.id, using psycopg2 safely

import os
import psycopg2
import psycopg2.extras
from types import SimpleNamespace
from typing import Any, Optional

DATABASE_URL = os.environ.get("DATABASE_URL")


class PsycopgSession:
    def __init__(self):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        self.conn = psycopg2.connect(DATABASE_URL)
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            try:
                self.cur.close()
            finally:
                self.conn.close()

    def execute(self, sql, params: tuple | dict = ()):
        if not isinstance(sql, str):
            sql = str(sql)
        self.cur.execute(sql, params or ())

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()

    def commit(self):
        self.conn.commit()


def get_session() -> PsycopgSession:
    return PsycopgSession()


# --------------------------------------------------------------------------------------
# SCHEMA bootstrap
# --------------------------------------------------------------------------------------

def ensure_schema() -> None:
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS "user" (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            trial_until TIMESTAMPTZ NULL,
            access_until TIMESTAMPTZ NULL,
            is_blocked BOOLEAN DEFAULT FALSE NOT NULL,
            is_active  BOOLEAN DEFAULT TRUE  NOT NULL,
            trial_start TIMESTAMPTZ NULL,
            trial_end   TIMESTAMPTZ NULL,
            license_until TIMESTAMPTZ NULL,
            trial_reminder_sent BOOLEAN DEFAULT FALSE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
            started_at TIMESTAMPTZ NULL,
            is_admin   BOOLEAN DEFAULT FALSE NOT NULL,
            countries  TEXT NULL,
            proposal_template TEXT NULL,
            name       TEXT NULL,
            username   TEXT NULL,
            keywords   TEXT NULL
        );
        """)

        # feed_event
        s.execute("""
        CREATE TABLE IF NOT EXISTS feed_event (
            id BIGSERIAL PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            original_url TEXT,
            affiliate_url TEXT,
            budget_amount NUMERIC(12,2),
            budget_currency TEXT,
            budget_usd NUMERIC(12,2),
            created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)

        # saved_job
        s.execute("""
        CREATE TABLE IF NOT EXISTS saved_job (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            feed_event_id BIGINT NOT NULL REFERENCES feed_event(id) ON DELETE CASCADE,
            saved_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)

        # unique index
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname='ux_saved_job_user_feed'
            ) THEN
                CREATE UNIQUE INDEX ux_saved_job_user_feed ON saved_job(user_id, feed_event_id);
            END IF;
        END$$;
        """)

        s.commit()


# --------------------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------------------

def get_or_create_user_by_tid(s_or_tid, maybe_tid: Optional[int] = None, username: Optional[str] = None):
    """Backward compatible: works with (session, tid) or (tid)."""
    if isinstance(s_or_tid, PsycopgSession):
        telegram_id = maybe_tid
        session = s_or_tid
        close_after = False
    else:
        telegram_id = s_or_tid
        session = get_session()
        close_after = True

    try:
        session.execute('SELECT * FROM "user" WHERE telegram_id = %s;', (telegram_id,))
        row = session.fetchone()

        if row:
            session.execute(
                'UPDATE "user" SET username = COALESCE(%s, username), is_active = TRUE WHERE telegram_id = %s RETURNING *;',
                (username, telegram_id),
            )
            updated = session.fetchone()
            session.commit()
            return SimpleNamespace(**updated)

        session.execute(
            'INSERT INTO "user" (telegram_id, username, is_active) VALUES (%s, %s, TRUE) RETURNING *;',
            (telegram_id, username),
        )
        created = session.fetchone()
        session.commit()
        return SimpleNamespace(**created)
    finally:
        if close_after:
            try:
                session.cur.close()
                session.conn.close()
            except Exception:
                pass
