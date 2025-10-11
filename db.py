import logging
from sqlalchemy import create_engine, text as _t
from sqlalchemy.orm import sessionmaker
import os

logger = logging.getLogger(__name__)

# ==========================================================
# Database Setup
# ==========================================================
DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def get_session():
    return SessionLocal()

# ==========================================================
# Basic user helper
# ==========================================================
def get_or_create_user_by_tid(s, tid: int):
    row = s.execute(_t('SELECT * FROM "user" WHERE telegram_id=:t'), {"t": tid}).fetchone()
    if row:
        return row
    s.execute(_t('INSERT INTO "user"(telegram_id, is_active, is_blocked) VALUES (:t, true, false)'), {"t": tid})
    s.commit()
    return s.execute(_t('SELECT * FROM "user" WHERE telegram_id=:t'), {"t": tid}).fetchone()

# ==========================================================
# Schema migration / ensure columns exist
# ==========================================================
def ensure_schema():
    """Ensures all needed tables/columns exist."""
    with engine.begin() as conn:
        try:
            conn.execute(_t("""
            ALTER TABLE "user" ADD COLUMN IF NOT EXISTS trial_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE;
            CREATE TABLE IF NOT EXISTS saved_job (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES "user"(id),
                job_id TEXT NULL,
                title TEXT NULL,
                description TEXT NULL,
                proposal_url TEXT NULL,
                original_url TEXT NULL,
                budget_amount TEXT NULL,
                budget_currency TEXT NULL,
                saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_saved_job_user ON saved_job(user_id);
            """))
        except Exception as e:
            logger.warning(f"migrate skip: {e}")
