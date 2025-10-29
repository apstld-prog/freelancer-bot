# db_keywords.py — fixed with get_all_user_keywords()

import logging
from sqlalchemy import text
from db import get_session

log = logging.getLogger("db_keywords")


# ---------------- Base Operations ----------------
def list_keywords(user_id: int):
    with get_session() as s:
        rows = s.execute(
            text('SELECT keyword FROM user_keywords WHERE user_id=:uid ORDER BY keyword'),
            {"uid": user_id}
        ).fetchall()
        return [r[0] for r in rows]


def add_keywords(user_id: int, keywords: list[str]) -> int:
    if not keywords:
        return 0
    inserted = 0
    with get_session() as s:
        for kw in keywords:
            try:
                s.execute(
                    text('INSERT INTO user_keywords (user_id, keyword) VALUES (:uid, :kw) ON CONFLICT DO NOTHING'),
                    {"uid": user_id, "kw": kw.lower()}
                )
                inserted += 1
            except Exception as e:
                log.warning("add_keywords error: %s", e)
        s.commit()
    return inserted


def delete_keywords(user_id: int, keywords: list[str]) -> int:
    if not keywords:
        return 0
    with get_session() as s:
        res = s.execute(
            text('DELETE FROM user_keywords WHERE user_id=:uid AND keyword=ANY(:kws)'),
            {"uid": user_id, "kws": keywords}
        )
        s.commit()
        return res.rowcount


def clear_keywords(user_id: int) -> int:
    with get_session() as s:
        res = s.execute(text('DELETE FROM user_keywords WHERE user_id=:uid'), {"uid": user_id})
        s.commit()
        return res.rowcount


def count_keywords(user_id: int) -> int:
    with get_session() as s:
        val = s.execute(text('SELECT COUNT(*) FROM user_keywords WHERE user_id=:uid'), {"uid": user_id}).scalar()
        return int(val or 0)


# ---------------- Admin Init / Utility ----------------
def ensure_keyword_unique():
    """Ensure that user_keywords table exists."""
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS user_keywords (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                keyword TEXT NOT NULL,
                UNIQUE(user_id, keyword)
            )
        """))
        s.commit()


def get_all_user_keywords() -> dict[int, list[str]]:
    """Return {user_id: [keywords...]} for all users."""
    out = {}
    with get_session() as s:
        rows = s.execute(text('SELECT user_id, keyword FROM user_keywords')).fetchall()
    for uid, kw in rows:
        out.setdefault(uid, []).append(kw)
    return out


# ---------------- Optional Default Initialization ----------------
def ensure_default_admin_keywords():
    """Ensure admin has base keywords if none exist."""
    with get_session() as s:
        admin = s.execute(text('SELECT id FROM "user" WHERE is_admin=TRUE LIMIT 1')).fetchone()
        if not admin:
            log.info("No admin user found.")
            return
        admin_id = admin[0]
        existing = s.execute(text('SELECT COUNT(*) FROM user_keywords WHERE user_id=:uid'),
                             {"uid": admin_id}).scalar()
        if existing and existing > 0:
            log.info("Admin already has keywords, no changes.")
            return
        defaults = ["logo", "lighting", "design", "marketing"]
        for kw in defaults:
            s.execute(text('INSERT INTO user_keywords (user_id, keyword) VALUES (:uid, :kw)'),
                      {"uid": admin_id, "kw": kw})
        s.commit()
        log.info("Default admin keywords inserted.")
