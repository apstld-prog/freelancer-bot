import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from db import get_session

log = logging.getLogger(__name__)

# ------------------------------------------------------
# USER HELPERS
# ------------------------------------------------------

def get_user(telegram_id: int):
    """Return user row or None."""
    with get_session() as db:
        row = db.execute(
            text("""
                SELECT telegram_id, countries, proposal_template, active, blocked,
                       start_date, trial_until, license_until
                FROM app_user
                WHERE telegram_id = :u
            """),
            {"u": telegram_id}
        ).fetchone()
        return row


def create_user_if_missing(telegram_id: int):
    """
    Creates a new user row if it does not exist.
    Returns the user row afterwards.
    """
    with get_session() as db:
        row = db.execute(
            text("SELECT telegram_id FROM app_user WHERE telegram_id = :u"),
            {"u": telegram_id}
        ).fetchone()

        if not row:
            log.info(f"Creating new user {telegram_id}")

            db.execute(
                text("""
                    INSERT INTO app_user (
                        telegram_id, countries, proposal_template,
                        active, blocked, start_date,
                        trial_until, license_until
                    )
                    VALUES (
                        :u, '', '', TRUE, FALSE, NOW(),
                        NOW() + INTERVAL '10 days', NULL
                    )
                """),
                {"u": telegram_id}
            )
            db.commit()

        # Return full user row
        row = db.execute(
            text("""
                SELECT telegram_id, countries, proposal_template, active, blocked,
                       start_date, trial_until, license_until
                FROM app_user
                WHERE telegram_id = :u
            """),
            {"u": telegram_id}
        ).fetchone()

        return row


def update_user_settings(telegram_id: int, **kwargs):
    """
    Generic update function: update only the columns provided.
    """
    if not kwargs:
        return

    set_parts = []
    params = {"u": telegram_id}

    for key, value in kwargs.items():
        set_parts.append(f"{key} = :{key}")
        params[key] = value

    sql = f"UPDATE app_user SET {', '.join(set_parts)} WHERE telegram_id = :u"

    with get_session() as db:
        db.execute(text(sql), params)
        db.commit()


def set_keywords(telegram_id: int, keywords: str):
    """Store comma-separated keyword string."""
    from db_keywords import save_keywords
    save_keywords(telegram_id, keywords)


def get_keywords(telegram_id: int):
    """Return list of saved keywords."""
    from db_keywords import fetch_keywords
    return fetch_keywords(telegram_id)


def is_admin_user(telegram_id: int):
    """Check if user is admin via config."""
    from config import ADMIN_IDS
    return telegram_id in ADMIN_IDS


# ------------------------------------------------------
# BASIC CLEAN FUNCTIONS
# ------------------------------------------------------

def clean_text(s: str) -> str:
    if not s:
        return ""
    return s.replace("\x00", "").strip()


def days_from_today(days: int):
    return datetime.utcnow() + timedelta(days=days)
