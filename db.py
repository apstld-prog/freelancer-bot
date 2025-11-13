# db.py - FIXED for workers (NO contextmanager)

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql+psycopg2"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2", "postgresql")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


# ----------------------------------------------------------
# RETURN REAL SESSION (NOT CONTEXT MANAGER)
# ----------------------------------------------------------
def get_session():
    """Return a real SQLAlchemy session."""
    return SessionLocal()


def close_session(s):
    try:
        s.close()
    except:
        pass


# ----------------------------------------------------------
# SCHEMA
# ----------------------------------------------------------
def ensure_schema():
    with engine.connect() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS "user" (LIKE "user" INCLUDING ALL)'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS keyword (LIKE keyword INCLUDING ALL)'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS feed_event (LIKE feed_event INCLUDING ALL)'))


# ----------------------------------------------------------
# USER HELPERS
# ----------------------------------------------------------
def get_or_create_user_by_tid(s, telegram_id: int):
    r = s.execute(
        text('SELECT * FROM "user" WHERE telegram_id=:tid'),
        {"tid": telegram_id}
    ).fetchone()

    if r:
        return r

    s.execute(
        text('INSERT INTO "user" (telegram_id) VALUES (:tid)'),
        {"tid": telegram_id}
    )
    return s.execute(
        text('SELECT * FROM "user" WHERE telegram_id=:tid'),
        {"tid": telegram_id}
    ).fetchone()


def update_user_fields(s, user_id: int, **fields):
    sets = ", ".join(f"{k}=:{k}" for k in fields)
    params = fields.copy()
    params["id"] = user_id
    s.execute(text(f'UPDATE "user" SET {sets} WHERE id=:id'), params)


# ----------------------------------------------------------
# KEYWORDS
# ----------------------------------------------------------
def list_keywords(s, user_id: int):
    return s.execute(
        text("SELECT keyword FROM keyword WHERE user_id=:id"),
        {"id": user_id}
    ).fetchall()


def add_keyword(s, user_id: int, keyword: str):
    s.execute(
        text("INSERT INTO keyword (user_id, keyword) VALUES (:id, :kw)"),
        {"id": user_id, "kw": keyword}
    )


def delete_keyword(s, user_id: int, keyword: str):
    s.execute(
        text("DELETE FROM keyword WHERE user_id=:id AND keyword=:kw"),
        {"id": user_id, "kw": keyword}
    )


# ----------------------------------------------------------
# FEED EVENTS
# ----------------------------------------------------------
def record_event(s, platform: str, sent: int):
    s.execute(
        text("INSERT INTO feed_event (platform, sent) VALUES (:p, :s)"),
        {"p": platform, "s": sent}
    )
