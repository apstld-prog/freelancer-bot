
# db.py — DB helpers used by workers
import os
import logging
import psycopg2
from contextlib import closing

logger = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL")

def _conn():
    return psycopg2.connect(DATABASE_URL, sslmode=os.getenv("PGSSLMODE", "require"))

async def get_user_keywords():
    """Return {telegram_id: [kw,...]} only for active, not-blocked users with keywords.
    Works against either 'user' table (new) or legacy 'users' + 'user_keywords' bridge.
    """
    mapping = {}

    with closing(_conn()) as conn, conn, conn.cursor() as cur:
        # Prefer modern 'user' table if present
        cur.execute("""
            SELECT 1 FROM information_schema.tables WHERE table_name='user'
        """)
        has_user = cur.fetchone() is not None

        if has_user:
            # keywords stored in JSON/text column 'keywords' OR via user_keywords table
            # Try direct column first
            cur.execute("""
                SELECT telegram_id, COALESCE(keywords, '')::text
                FROM "user"
                WHERE COALESCE(is_active, TRUE) = TRUE
                  AND COALESCE(is_blocked, FALSE) = FALSE
            """)
            rows = cur.fetchall()
            for tid, kwtext in rows:
                if not tid: 
                    continue
                kws = []
                if kwtext:
                    # support either comma-separated or JSON-ish list
                    txt = kwtext.strip()
                    if txt.startswith('['):
                        try:
                            import json
                            kws = [k.strip() for k in json.loads(txt) if k and isinstance(k, str)]
                        except Exception:
                            pass
                    if not kws:
                        kws = [k.strip() for k in kwtext.split(',') if k.strip()]
                if kws:
                    mapping[int(tid)] = kws

            # If nothing found and user_keywords exists, fallback to that
            if not mapping:
                cur.execute("""
                    SELECT u.telegram_id, uk.keyword
                    FROM "user" u
                    JOIN user_keywords uk ON uk.user_id = u.id
                    WHERE COALESCE(u.is_active, TRUE) = TRUE
                      AND COALESCE(u.is_blocked, FALSE) = FALSE
                """)
                agg = {}
                for tid, kw in cur.fetchall():
                    if not tid or not kw:
                        continue
                    agg.setdefault(int(tid), set()).add(kw.strip())
                for tid, s in agg.items():
                    if s:
                        mapping[tid] = sorted(s)
            return mapping

        # Legacy path: 'users' table + 'user_keywords' bridge
        cur.execute("""
            SELECT 1 FROM information_schema.columns 
             WHERE table_name='users' AND column_name='telegram_id'
        """)
        has_legacy = cur.fetchone() is not None

        if has_legacy:
            cur.execute("""
                SELECT u.telegram_id, uk.keyword
                FROM users u
                JOIN user_keywords uk ON uk.user_id = u.id
                WHERE COALESCE(u.is_active, TRUE) = TRUE
                  AND COALESCE(u.is_blocked, FALSE) = FALSE
            """)
            agg = {}
            for tid, kw in cur.fetchall():
                if not tid or not kw:
                    continue
                agg.setdefault(int(tid), set()).add(kw.strip())
            for tid, s in agg.items():
                if s:
                    mapping[tid] = sorted(s)
        return mapping
