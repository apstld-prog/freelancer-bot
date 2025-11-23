# db_keywords.py — FULL & FIXED

from sqlalchemy import text
from db import get_session

# ---------------------------------
# Add keyword
# ---------------------------------
def add_keyword(user_id: int, keyword: str):
    with get_session() as session:
        session.execute(
            text("INSERT INTO keyword (telegram_id, value) VALUES (:uid, :kw)"),
            {"uid": user_id, "kw": keyword},
        )
        session.commit()

# ---------------------------------
# Delete keyword
# ---------------------------------
def delete_keyword(user_id: int, keyword: str):
    with get_session() as session:
        session.execute(
            text("DELETE FROM keyword WHERE telegram_id = :uid AND value = :kw"),
            {"uid": user_id, "kw": keyword},
        )
        session.commit()

# ---------------------------------
# Get keywords for a specific user
# (legacy compatibility)
# ---------------------------------
def get_keywords(user_id: int):
    with get_session() as session:
        rows = session.execute(
            text("SELECT value FROM keyword WHERE telegram_id = :uid"),
            {"uid": user_id},
        ).fetchall()
    return rows

# ---------------------------------
# NEW — list_keywords (used by bot.py)
# ---------------------------------
def list_keywords(user_id: int):
    """
    Required by bot.py (/keywords).
    Returns Row objects with `.value`
    """
    with get_session() as session:
        rows = session.execute(
            text("SELECT value FROM keyword WHERE telegram_id = :uid"),
            {"uid": user_id},
        ).fetchall()
    return rows

# ---------------------------------
# GLOBAL — used by unified worker
# returns Row(keyword="logo")
# ---------------------------------
def get_all_keywords():
    """
    Return ALL keywords for ALL users.
    Row objects with attribute `.keyword`
    """
    with get_session() as session:
        rows = session.execute(
            text("SELECT value AS keyword FROM keyword")
        ).fetchall()
    return rows
