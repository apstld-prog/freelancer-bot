
from db import get_session
from sqlalchemy import text as _t

def ensure_trial_notice_schema():
    with get_session() as s:
        s.execute(_t("""
        CREATE TABLE IF NOT EXISTS trial_notice (
            user_id INTEGER PRIMARY KEY,
            sent_day_before BOOLEAN NOT NULL DEFAULT FALSE,
            sent_on_expiry BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
        )
        """))
        s.commit()

def mark_day_before_sent(user_id: int):
    with get_session() as s:
        s.execute(_t("""
        INSERT INTO trial_notice(user_id, sent_day_before)
        VALUES (:u, TRUE)
        ON CONFLICT (user_id) DO UPDATE SET
            sent_day_before = TRUE,
            updated_at = (NOW() AT TIME ZONE 'UTC')
        """), {"u": user_id})
        s.commit()

def has_day_before_sent(user_id: int) -> bool:
    with get_session() as s:
        row = s.execute(_t('SELECT sent_day_before FROM trial_notice WHERE user_id=:u'), {"u": user_id}).fetchone()
        return bool(row and row[0])
