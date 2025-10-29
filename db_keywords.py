import logging
from sqlalchemy import text
from db import get_session

log = logging.getLogger("db_keywords")

# Default keywords for admin (only added if admin has none)
DEFAULT_KEYWORDS = ["logo", "lighting", "design"]

# -----------------------------------------------------------
# List keywords for a given user
# -----------------------------------------------------------
def list_keywords(user_id: int):
    try:
        with get_session() as s:
            rows = s.execute(text('SELECT keyword FROM user_keywords WHERE user_id=:uid ORDER BY keyword ASC'),
                             {"uid": user_id}).fetchall()
            return [r[0] for r in rows]
    except Exception as e:
        log.error(f"[list_keywords] {e}")
        return []


# -----------------------------------------------------------
# Count keywords for user
# -----------------------------------------------------------
def count_keywords(user_id: int) -> int:
    try:
        with get_session() as s:
            n = s.execute(text('SELECT COUNT(*) FROM user_keywords WHERE user_id=:uid'),
                          {"uid": user_id}).scalar()
            return int(n or 0)
    except Exception as e:
        log.error(f"[count_keywords] {e}")
        return 0


# -----------------------------------------------------------
# Add new keywords (no duplicates)
# -----------------------------------------------------------
def add_keywords(user_id: int, keywords):
    inserted = 0
    if not keywords:
        return 0
    with get_session() as s:
        for kw in keywords:
            kw = kw.strip().lower()
            if not kw:
                continue
            # check if exists
            exists = s.execute(text('SELECT 1 FROM user_keywords WHERE user_id=:uid AND keyword=:kw'),
                               {"uid": user_id, "kw": kw}).fetchone()
            if not exists:
                s.execute(text('INSERT INTO user_keywords (user_id, keyword) VALUES (:uid, :kw)'),
                          {"uid": user_id, "kw": kw})
                inserted += 1
        s.commit()
    return inserted


# -----------------------------------------------------------
# Delete selected keywords
# -----------------------------------------------------------
def delete_keywords(user_id: int, keywords):
    if not keywords:
        return 0
    with get_session() as s:
        res = s.execute(
            text('DELETE FROM user_keywords WHERE user_id=:uid AND keyword = ANY(:kws) RETURNING keyword'),
            {"uid": user_id, "kws": keywords},
        ).fetchall()
        s.commit()
    return len(res or [])


# -----------------------------------------------------------
# Clear all keywords for user
# -----------------------------------------------------------
def clear_keywords(user_id: int):
    with get_session() as s:
        res = s.execute(text('DELETE FROM user_keywords WHERE user_id=:uid RETURNING keyword'),
                        {"uid": user_id}).fetchall()
        s.commit()
    return len(res or [])


# -----------------------------------------------------------
# Ensure that each user has their keywords table
# -----------------------------------------------------------
def ensure_keywords_table():
    """Ensures user_keywords table exists."""
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


# -----------------------------------------------------------
# Safe initialization — does NOT erase any existing data
# -----------------------------------------------------------
def ensure_keyword_unique():
    """
    Ensures the user_keywords table exists and admin has at least defaults.
    Does NOT touch existing keywords.
    """
    ensure_keywords_table()
    try:
        with get_session() as s:
            admin = s.execute(text('SELECT id FROM "user" WHERE is_admin=TRUE LIMIT 1')).fetchone()
            if not admin:
                log.info("No admin found, skipping default keywords seed.")
                return
            admin_id = admin[0]
            existing = s.execute(text('SELECT keyword FROM user_keywords WHERE user_id=:a'), {"a": admin_id}).fetchall()
            existing_set = {r[0].lower() for r in existing}
            to_add = [kw for kw in DEFAULT_KEYWORDS if kw.lower() not in existing_set]
            if to_add:
                for kw in to_add:
                    s.execute(text('INSERT INTO user_keywords (user_id, keyword) VALUES (:a, :k)'),
                              {"a": admin_id, "k": kw})
                s.commit()
                log.info(f"Added {len(to_add)} default keyword(s) to admin.")
            else:
                log.info("Admin already has keywords, no changes.")
    except Exception as e:
        log.error(f"[ensure_keyword_unique] {e}")
