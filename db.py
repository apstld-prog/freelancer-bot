import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import closing

logger = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL")

# ----------------------------------------------------
# Basic connection helper
# ----------------------------------------------------
def _conn():
    return psycopg2.connect(DATABASE_URL, sslmode=os.getenv("PGSSLMODE", "require"))

# ----------------------------------------------------
# Ensure database schema (used at startup)
# ----------------------------------------------------
def ensure_schema():
    """Ensure required tables exist."""
    with closing(_conn()) as conn, conn, conn.cursor() as cur:
        logger.info("[DB] Ensuring base schema...")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS "user" (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            is_admin BOOLEAN DEFAULT FALSE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE NOT NULL,
            is_blocked BOOLEAN DEFAULT FALSE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_keywords (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES "user"(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS job_event (
            id SERIAL PRIMARY KEY,
            platform TEXT,
            title TEXT,
            description TEXT,
            affiliate_url TEXT,
            original_url TEXT,
            budget_amount NUMERIC,
            budget_currency TEXT,
            created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)

        conn.commit()
        logger.info("[DB] ✅ Schema ensured")

# ----------------------------------------------------
# SQLAlchemy-like session placeholder
# ----------------------------------------------------
def get_session():
    """Provide simple psycopg2 connection for compatibility."""
    return _conn()

# ----------------------------------------------------
# Create or update a user by Telegram ID
# ----------------------------------------------------
def get_or_create_user_by_tid(tg_id: int, username: str = None):
    """Ensure a user exists in the 'user' table."""
    with closing(_conn()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
        SELECT * FROM "user" WHERE telegram_id = %s;
        """, (tg_id,))
        row = cur.fetchone()

        if row:
            # Update username if changed
            if username and row.get("username") != username:
                cur.execute("""
                    UPDATE "user"
                    SET username=%s, updated_at=NOW() AT TIME ZONE 'UTC'
                    WHERE telegram_id=%s;
                """, (username, tg_id))
                conn.commit()
            return row

        # Insert new user
        cur.execute("""
            INSERT INTO "user" (telegram_id, username, is_active, is_admin, is_blocked, created_at, updated_at)
            VALUES (%s, %s, TRUE, FALSE, FALSE, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
            RETURNING *;
        """, (tg_id, username))
        row = cur.fetchone()
        conn.commit()
        return row

# ----------------------------------------------------
# Get all user keywords (for workers)
# ----------------------------------------------------
async def get_user_keywords():
    """Return {telegram_id: [kw,...]} for active, non-blocked users."""
    mapping = {}

    with closing(_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("""
            SELECT u.telegram_id, uk.keyword
            FROM "user" u
            LEFT JOIN user_keywords uk ON uk.user_id = u.id
            WHERE COALESCE(u.is_active, TRUE) = TRUE
              AND COALESCE(u.is_blocked, FALSE) = FALSE
        """)
        agg = {}
        for tid, kw in cur.fetchall():
            if not tid:
                continue
            if kw:
                agg.setdefault(int(tid), set()).add(kw.strip())
        for tid, kws in agg.items():
            mapping[tid] = sorted(kws)
    return mapping
