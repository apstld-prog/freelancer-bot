import logging
from sqlalchemy import text
from db import get_session, close_session

log = logging.getLogger("utils")

# ----------------------------------------------------------
# CREATE OR FETCH USER
# ----------------------------------------------------------
def get_or_create_user_by_tid(tid: int):
    db = get_session()
    try:
        row = db.execute(
            text("SELECT id FROM app_user WHERE telegram_id=:t"),
            {"t": tid}
        ).fetchone()

        if row:
            return row[0]

        new_id = db.execute(
            text("""
                INSERT INTO app_user (telegram_id)
                VALUES (:t)
                RETURNING id
            """),
            {"t": tid}
        ).fetchone()[0]

        db.commit()
        return new_id
    finally:
        close_session(db)


# Compatibility wrapper
def get_user_id(tid: int):
    return get_or_create_user_by_tid(tid)


# ----------------------------------------------------------
# LOAD USER SETTINGS
# ----------------------------------------------------------
def get_user(tid: int):
    db = get_session()
    try:
        row = db.execute(
            text("""
                SELECT telegram_id, countries, proposal_template, active, blocked,
                       start_date, trial_until, license_until
                FROM app_user
                WHERE telegram_id=:u
            """),
            {"u": tid}
        ).fetchone()

        if not row:
            return None

        return {
            "telegram_id": row[0],
            "countries": row[1],
            "proposal_template": row[2],
            "active": row[3],
            "blocked": row[4],
            "start_date": row[5],
            "trial_until": row[6],
            "license_until": row[7]
        }
    finally:
        close_session(db)


# ----------------------------------------------------------
# UPDATE USER SETTINGS
# ----------------------------------------------------------
def set_user_setting(tid: int, field: str, value):
    db = get_session()
    try:
        db.execute(
            text(f"UPDATE app_user SET {field}=:v WHERE telegram_id=:u"),
            {"v": value, "u": tid}
        )
        db.commit()
    finally:
        close_session(db)


# ----------------------------------------------------------
# SAVE / DELETE JOB
# ----------------------------------------------------------
def save_job(tid: int, job_id: str):
    db = get_session()
    try:
        db.execute(
            text("""
                INSERT INTO saved_job (user_id, job_id)
                VALUES (:u, :j)
                ON CONFLICT DO NOTHING;
            """),
            {"u": tid, "j": job_id}
        )
        db.commit()
    finally:
        close_session(db)


def delete_saved_job(tid: int, job_id: str):
    db = get_session()
    try:
        db.execute(
            text("DELETE FROM saved_job WHERE user_id=:u AND job_id=:j"),
            {"u": tid, "j": job_id}
        )
        db.commit()
    finally:
        close_session(db)


# ----------------------------------------------------------
# AFFILIATE WRAPPER
# ----------------------------------------------------------
def wrap_affiliate_link(url: str) -> str:
    if not url:
        return url
    return f"https://track.freelancer.com/c/YOUR_F_AFF_ID/?url={url}"
