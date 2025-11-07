# db_keywords.py — keyword management helpers for users
import logging
from typing import List, Dict
from datetime import datetime, timezone
from sqlalchemy import text
from db import get_session

log = logging.getLogger("db_keywords")


def ensure_keywords_schema():
    """Ensure keyword table exists."""
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS keyword (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                value TEXT NOT NULL,
                keyword TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
            );
        """))
        s.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_keyword_user_value
            ON keyword(user_id, value);
        """))
        s.commit()


def list_keywords(user_id: int) -> List[str]:
    """Return list of keywords for given user."""
    with get_session() as s:
        rows = s.execute(
            text("SELECT value FROM keyword WHERE user_id=:uid ORDER BY id ASC"),
            {"uid": user_id}
        ).fetchall()
        return [r[0] for r in rows]


def add_keywords(user_id: int, keywords: List[str]) -> int:
    """Add unique keywords for a user (with created_at fix)."""
    if not keywords:
        return 0
    with get_session() as s:
        existing = {
            r[0] for r in s.execute(
                text("SELECT value FROM keyword WHERE user_id=:uid"),
                {"uid": user_id}
            ).fetchall()
        }
        inserted = 0
        for kw in keywords:
            v = kw.strip().lower()
            if not v or v in existing:
                continue

            now = datetime.now(timezone.utc)
            s.execute(
                text("""
                    INSERT INTO keyword (user_id, value, keyword, created_at, updated_at)
                    VALUES (:uid, :val, :val, :created_at, :updated_at)
                """),
                {"uid": user_id, "val": v, "created_at": now, "updated_at": now}
            )
            inserted += 1

        if inserted:
            s.commit()
        return inserted


def delete_keywords(user_id: int, keywords: List[str]) -> int:
    """Delete selected keywords."""
    if not keywords:
        return 0
    with get_session() as s:
        r = s.execute(
            text("DELETE FROM keyword WHERE user_id=:uid AND value = ANY(:vals) RETURNING id"),
            {"uid": user_id, "vals": keywords}
        )
        s.commit()
        return r.rowcount


def clear_keywords(user_id: int) -> int:
    """Remove all keywords for a user."""
    with get_session() as s:
        r = s.execute(
            text("DELETE FROM keyword WHERE user_id=:uid RETURNING id"),
            {"uid": user_id}
        )
        s.commit()
        return r.rowcount


def count_keywords(user_id: int) -> int:
    """Return count of user's keywords."""
    with get_session() as s:
        n = s.execute(
            text("SELECT COUNT(*) FROM keyword WHERE user_id=:uid"),
            {"uid": user_id}
        ).scalar()
        return int(n or 0)


def ensure_keyword_unique():
    """Ensure unique index exists."""
    with get_session() as s:
        s.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_keyword_user_value
            ON keyword(user_id, value);
        """))
        s.commit()


def get_all_user_keywords(db=None) -> Dict[int, List[str]]:
    """Return a dictionary of {telegram_id: [keywords...]} for all active users."""
    close_it = False
    if db is None:
        db = get_session()
        close_it = True
    q = text("""
        SELECT u.telegram_id, k.value
        FROM "user" u
        LEFT JOIN keyword k ON u.id = k.user_id
        WHERE u.is_active=TRUE AND u.is_blocked=FALSE
        ORDER BY u.id, k.id
    """)
    rows = db.execute(q).fetchall()
    out: Dict[int, List[str]] = {}
    for tid, val in rows:
        if not tid:
            continue
        if tid not in out:
            out[tid] = []
        if val:
            out[tid].append(val)
    if close_it:
        db.close()
    return out
