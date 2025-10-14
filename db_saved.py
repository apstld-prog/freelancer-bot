
from contextlib import contextmanager
from sqlalchemy import text as _t
from db import get_session

def ensure_saved_schema():
    with get_session() as s:
        s.execute(_t("""
        CREATE TABLE IF NOT EXISTS saved_job (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT,
            url TEXT,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
        )
        """))
        s.commit()

def add_saved_job(user_id: int, title: str, url: str, description: str = "") -> int:
    with get_session() as s:
        row = s.execute(
            _t('INSERT INTO saved_job(user_id, title, url, description) VALUES (:u,:t,:uurl,:d) RETURNING id'),
            {"u": user_id, "t": title, "uurl": url, "d": description}
        ).fetchone()
        s.commit()
        return int(row[0]) if row else 0

def list_saved_jobs(user_id: int, limit: int = 25):
    with get_session() as s:
        rows = s.execute(
            _t('SELECT id, title, url, description, created_at FROM saved_job WHERE user_id=:u ORDER BY id DESC LIMIT :lim'),
            {"u": user_id, "lim": limit}
        ).fetchall()
        return rows or []

def delete_saved_job(user_id: int, saved_id: int) -> bool:
    with get_session() as s:
        rc = s.execute(_t('DELETE FROM saved_job WHERE id=:i AND user_id=:u'), {"i": saved_id, "u": user_id}).rowcount
        if rc: s.commit()
        return rc > 0

def clear_saved_jobs(user_id: int) -> int:
    with get_session() as s:
        rc = s.execute(_t('DELETE FROM saved_job WHERE user_id=:u'), {"u": user_id}).rowcount
        if rc: s.commit()
        return int(rc or 0)
