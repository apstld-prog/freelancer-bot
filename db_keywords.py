import logging
from sqlalchemy import text
from db import get_session, close_session

log = logging.getLogger("db_keywords")


# ----------------------------------------------------------
# ENSURE SCHEMA — USES TABLE `keyword`, NOT `user_keywords`
# ----------------------------------------------------------
def ensure_keywords_schema():
    """Ensures keyword table exists."""
    db = get_session()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS keyword (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                keyword TEXT NOT NULL
            );
        """))
        db.commit()
    finally:
        close_session(db)


# ----------------------------------------------------------
# GET ALL KEYWORDS FOR A USER
# ----------------------------------------------------------
def get_keywords(user_id: int):
    db = get_session()
    try:
        rows = db.execute(
            text("SELECT keyword FROM keyword WHERE user_id=:u"),
            {"u": user_id}
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        close_session(db)


# ----------------------------------------------------------
# ADD MULTIPLE KEYWORDS
# ----------------------------------------------------------
def add_keywords(user_id: int, keywords):
    db = get_session()
    try:
        for kw in keywords:
            db.execute(
                text("INSERT INTO keyword (user_id, keyword) VALUES (:u, :k)"),
                {"u": user_id, "k": kw}
            )
        db.commit()
    finally:
        close_session(db)


# ----------------------------------------------------------
# DELETE ONE KEYWORD
# ----------------------------------------------------------
def delete_keyword(user_id: int, keyword: str):
    db = get_session()
    try:
        db.execute(
            text("DELETE FROM keyword WHERE user_id=:u AND keyword=:k"),
            {"u": user_id, "k": keyword}
        )
        db.commit()
    finally:
        close_session(db)


# ----------------------------------------------------------
# WORKER COMPATIBILITY METHOD
# ----------------------------------------------------------
def get_keywords_for_user(telegram_id: int):
    """Workers use this (same as get_keywords)."""
    return get_keywords(telegram_id)
