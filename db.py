import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import closing

logger = logging.getLogger("db")
DATABASE_URL = os.getenv("DATABASE_URL")

# ====================================================
# Internal connection helper
# ====================================================
def _conn():
    return psycopg2.connect(DATABASE_URL, sslmode=os.getenv("PGSSLMODE", "require"))

# ====================================================
# SQLAlchemy-like wrapper (για συμβατότητα)
# ====================================================
class PsycopgSession:
    def __init__(self):
        self.conn = _conn()
        self.cur = self.conn.cursor()

    def execute(self, sql, params=None):
        self.cur.execute(sql, params or ())
        try:
            return self.cur.fetchall()
        except psycopg2.ProgrammingError:
            # e.g. no results
            return []

    def connection(self):
        """Return the psycopg2 connection (for legacy code)."""
        return self.conn

    def commit(self):
        self.conn.commit()

    def close(self):
        try:
            self.cur.close()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

# ====================================================
# Ensure database schema
# ====================================================
def ensure_schema():
    with closing(_conn()) as conn, conn, conn.cursor() as cur:
        logger.info("[DB] Ensuring schema...")

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

# ====================================================
# get_session (συμβατό με legacy scripts)
# ====================================================
def get_session():
    return PsycopgSession()

# ====================================================
# get_or_create_user_by_tid
# ====================================================
def get_or_create_user_by_tid(tg_id: int, username: str = None):
    with closing(_conn()) as conn, conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT * FROM "user" WHERE telegram_id = %s;""", (tg_id,))
        row = cur.fetchone()
        if row:
            if username and row.get("username") != username:
                cur.execute("""
                    UPDATE "user"
                    SET username=%s, updated_at=NOW() AT TIME ZONE 'UTC'
                    WHERE telegram_id=%s;
                """, (username, tg_id))
                conn.commit()
            return row

        cur.execute("""
            INSERT INTO "user" (telegram_id, username, is_active, is_admin, is_blocked, created_at, updated_at)
            VALUES (%s, %s, TRUE, FALSE, FALSE, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
            RETURNING *;
        """, (tg_id, username))
        row = cur.fetchone()
        conn.commit()
        return row

# ====================================================
# get_user_keywords (used by workers)
# ====================================================
async def get_user_keywords():
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
