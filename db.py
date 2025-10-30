# db.py
# Psycopg2-only DB helper layer + minimal schema bootstrap + helpers used by bot.py

import os
import psycopg2
import psycopg2.extras
from typing import Any, Iterable, Optional


DATABASE_URL = os.environ.get("DATABASE_URL")


class PsycopgSession:
    def __init__(self):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        self.conn = psycopg2.connect(DATABASE_URL)
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # context manager
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

    # basic ops (accepts str or SQLAlchemy TextClause)
    def execute(self, sql, params: tuple | dict = ()):
        # Accept both str and SQLAlchemy TextClause
        if not isinstance(sql, str):
            try:
                sql = str(sql)
            except Exception:
                sql = getattr(sql, "text", sql)
        self.cur.execute(sql, params or ())

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()

    def commit(self):
        self.conn.commit()


def get_session() -> PsycopgSession:
    """Return a new PsycopgSession. Use with: `with get_session() as s:`"""
    return PsycopgSession()


# --------------------------------------------------------------------------------------
# SCHEMA
# --------------------------------------------------------------------------------------

def ensure_schema() -> None:
    """
    Create minimal tables used across the app if missing.
    Uses quoted "user" to avoid reserved-word issues.
    """
    with get_session() as s:
        # "user" table
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
        # trigger to auto-update updated_at
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_user_updated_at'
            ) THEN
                CREATE OR REPLACE FUNCTION set_user_updated_at()
                RETURNS TRIGGER AS $BODY$
                BEGIN
                    NEW.updated_at := NOW() AT TIME ZONE 'UTC';
                    RETURN NEW;
                END;
                $BODY$ LANGUAGE plpgsql;

                CREATE TRIGGER trg_user_updated_at
                BEFORE UPDATE ON "user"
                FOR EACH ROW
                EXECUTE PROCEDURE set_user_updated_at();
            END IF;
        END$$;
        """)

        # saved_job table
        s.execute("""
        CREATE TABLE IF NOT EXISTS saved_job (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            job_id  BIGINT NOT NULL,
            saved_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname='ux_saved_job_user_job'
            ) THEN
                CREATE UNIQUE INDEX ux_saved_job_user_job ON saved_job(user_id, job_id);
            END IF;
        END$$;
        """)
        s.commit()


# --------------------------------------------------------------------------------------
# HELPERS USED BY bot.py
# --------------------------------------------------------------------------------------

def get_or_create_user_by_tid(telegram_id: int, username: Optional[str] = None) -> dict:
    """
    Ensure a user exists for given telegram_id. Returns row dict (id, telegram_id, ...).
    Marks is_active TRUE by default.
    """
    with get_session() as s:
        s.execute('SELECT * FROM "user" WHERE telegram_id = %s;', (telegram_id,))
        row = s.fetchone()
        if row:
            # update username + ensure active
            s.execute(
                'UPDATE "user" SET username = COALESCE(%s, username), is_active = TRUE WHERE telegram_id = %s RETURNING *;',
                (username, telegram_id)
            )
            updated = s.fetchone()
            s.commit()
            return dict(updated)

        # insert new
        s.execute(
            'INSERT INTO "user" (telegram_id, username, is_active) VALUES (%s, %s, TRUE) RETURNING *;',
            (telegram_id, username)
        )
        created = s.fetchone()
        s.commit()
        return dict(created)
