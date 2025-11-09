import logging
from sqlalchemy import text
from db import get_session, close_session

log = logging.getLogger("utils")


# --------------------------------------------
# BASIC USER FUNCTIONS
# --------------------------------------------
def get_user(user_id: int):
    db = get_session()
    try:
        row = db.execute(
            text("""
                SELECT telegram_id, countries, proposal_template, active, blocked
                FROM app_user
                WHERE telegram_id=:u
            """),
            {"u": user_id}
        ).fetchone()

        if not row:
            return None

        return {
            "telegram_id": row[0],
            "countries": row[1],
            "proposal_template": row[2],
            "active": row[3],
            "blocked": row[4]
        }

    finally:
        close_session(db)


def set_user_setting(user_id: int, field: str, value):
    db = get_session()
    try:
        db.execute(
            text(f"UPDATE app_user SET {field}=:v WHERE telegram_id=:u"),
            {"v": value, "u": user_id}
        )
        db.commit()
    finally:
        close_session(db)


# --------------------------------------------
# JOB STORAGE (SAVE / DELETE)
# --------------------------------------------
def save_job(user_id: int, job_id: str):
    db = get_session()
    try:
        db.execute(
            text("""
                INSERT INTO saved_job (user_id, job_id)
                VALUES (:u, :j)
                ON CONFLICT DO NOTHING;
            """),
            {"u": user_id, "j": job_id}
        )
        db.commit()
    finally:
        close_session(db)


def delete_saved_job(user_id: int, job_id: str):
    db = get_session()
    try:
        db.execute(
            text("DELETE FROM saved_job WHERE user_id=:u AND job_id=:j"),
            {"u": user_id, "j": job_id}
        )
        db.commit()
    finally:
        close_session(db)


# --------------------------------------------
# AFFILIATE WRAPPER
# --------------------------------------------
def wrap_affiliate_link(url: str) -> str:
    if not url:
        return url
    return f"https://track.freelancer.com/c/YOUR_F_AFF_ID/?url={url}"

