import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
)

Base = declarative_base()

def get_session():
    return SessionLocal()

def close_session(db):
    try:
        db.close()
    except:
        pass

def get_or_create_user_by_tid(tid: int):
    db = get_session()
    try:
        res = db.execute(
            text("SELECT id FROM app_user WHERE telegram_id=:t"),
            {"t": tid}
        ).fetchone()

        if res:
            return res[0]

        new = db.execute(
            text("INSERT INTO app_user (telegram_id) VALUES (:t) RETURNING id"),
            {"t": tid}
        ).fetchone()[0]

        db.commit()
        return new

    finally:
        close_session(db)
