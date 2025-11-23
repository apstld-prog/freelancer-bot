# db_keywords.py — FULL & FINAL FIXED VERSION

from sqlalchemy import text
from db import get_session

# ----------------------------------------------------
# Add ONE keyword
# ----------------------------------------------------
def add_keyword(user_id: int, keyword: str):
    with get_session() as session:
        session.execute(
            text("INSERT INTO keyword (telegram_id, value) VALUES (:uid, :kw)"),
            {"uid": user_id, "kw": keyword},
        )
        session.commit()

# ----------------------------------------------------
# Add MULTIPLE keywords (bot.py expects this)
# ----------------------------------------------------
def add_keywords(user_id: int, keywords: list[str]):
    """
    Required by bot.py.
    Bulk insert keywords — simply calls add_keyword() repeatedly.
    """
    for kw in keywords:
        add_keyword(user_id, kw)

# ----------------------------------------------------
# Delete keyword
# ----------------------------------------------------
def delete_keyword(user_id: int, keyword: str):
    with get_session() as session:
        session.execute(
            text("DELETE FROM keyword WHERE telegram_id = :uid AND value = :kw"),
            {"uid": user_id, "kw": keyword},
        )
        session.commit()

# ----------------------------------------------------
# Get keywords for a user (legacy)
# ----------------------------------------------------
def get_keywords(user_id: int):
    with get_session() as session:
        rows = session.execute(
            text("SELECT value FROM keyword WHERE telegram_id = :uid"),
            {"uid": user_id},
        ).fetchall()
    return rows

# ----------------------------------------------------
# list_keywords — REQUIRED BY bot.py (/keywords)
# ----------------------------------------------------
def list_keywords(user_id: int):
    """
    Returns Row objects with .value
    """
    with get_session() as session:
        rows = session.execute(
            text("SELECT value FROM keyword WHERE telegram_id = :uid"),
            {"uid": user_id},
        ).fetchall()
    return rows

# ----------------------------------------------------
# get_all_keywords — used by unified worker
# returns Row(keyword="logo")
# ----------------------------------------------------
def get_all_keywords():
    """
    Returns ALL keywords for ALL users.
    Produces Row objects with attribute `.keyword`
    """
    with get_session() as session:
        rows = session.execute(
            text("SELECT value AS keyword FROM keyword")
        ).fetchall()
    return rows
