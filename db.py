import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is missing in environment variables")

# Create engine (Render Postgres)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# Session factory
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
)

Base = declarative_base()


def get_session():
    """
    Returns a new SQLAlchemy session.
    Used everywhere (bot, workers, API).
    """
    try:
        db = SessionLocal()
        return db
    except Exception as e:
        raise RuntimeError(f"❌ Failed to create DB session: {e}")


def close_session(db):
    """
    Cleanly close a session.
    """
    try:
        db.close()
    except Exception:
        pass

