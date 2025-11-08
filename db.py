import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

log = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is missing in environment variables")

# Engine για Render Postgres
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Global session factory
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
)

Base = declarative_base()


def get_session():
    """Return a SQLAlchemy session."""
    try:
        return SessionLocal()
    except Exception as e:
        raise RuntimeError(f"❌ Failed to create DB session: {e}")


def close_session(db):
    """Cleanly close a session."""
    try:
        db.close()
    except Exception:
        pass


# ✅ NEW: AUTOMATIC DATABASE SCHEMA ENSURE
def ensure_schema():
    """
    Ensures that required tables exist with correct columns.
    Safe for repeated execution. No locks. No deadlocks.
    """
    log.info("✅ Ensuring database schema...")

    with engine.begin() as conn:

        # Users table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # Keywords table (used by workers)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS keyword (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

        # feed_event table (job cache)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feed_event (
                id SERIAL PRIMARY KEY,
                platform VARCHAR(50) NOT NULL,
                external_id VARCHAR(255) NOT NULL,
                title TEXT,
                description TEXT,
                affiliate_url TEXT,
                original_url TEXT,
                budget_amount FLOAT,
                budget_currency VARCHAR(20),
                budget_usd FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

    log.info("✅ Database schema OK")
