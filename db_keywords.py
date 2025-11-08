from sqlalchemy import text
from db import get_session, close_session


def get_keywords_for_user(user_id: int):
    """
    Returns a list of keyword strings for the given user.
    Used by all workers.
    """
    db = get_session()
    try:
        rows = db.execute(
            text("SELECT value FROM keyword WHERE user_id = :uid ORDER BY id ASC"),
            {"uid": user_id}
        ).fetchall()

        return [r[0] for r in rows if r[0]]
    finally:
        close_session(db)


def add_keyword(user_id: int, value: str):
    """
    Insert a new keyword for a user.
    """
    db = get_session()
    try:
        db.execute(
            text("INSERT INTO keyword (user_id, value) VALUES (:uid, :val)"),
            {"uid": user_id, "val": value}
        )
        db.commit()
    finally:
        close_session(db)


def delete_keyword(user_id: int, value: str):
    """
    Delete a keyword for a user.
    """
    db = get_session()
    try:
        db.execute(
            text("DELETE FROM keyword WHERE user_id = :uid AND value = :val"),
            {"uid": user_id, "val": value}
        )
        db.commit()
    finally:
        close_session(db)
