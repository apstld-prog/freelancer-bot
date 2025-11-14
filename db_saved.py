# db_saved.py — saved jobs table (portable)

from typing import List, Dict
from sqlalchemy import text
from db import get_session

def ensure_saved_schema() -> None:
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS saved_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                description TEXT,
                saved_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
            )
        """))
        s.commit()

def add_saved_job(user_id: int, title: str, url: str = "", description: str = "") -> int:
    ensure_saved_schema()
    with get_session() as s:
        row = s.execute(
            text("INSERT INTO saved_job (user_id,title,url,description) VALUES (:u,:t,:uurl,:d) RETURNING id"),
            {"u": user_id, "t": title, "uurl": url, "d": description}
        ).fetchone()
        s.commit()
        return int(row[0]) if row else 0

def list_saved_jobs_by_user(user_id: int, limit: int = 10) -> List[Dict]:
    ensure_saved_schema()
    limit = int(limit) if limit and int(limit) > 0 else 10
    with get_session() as s:
        rows = s.execute(
            text(f"SELECT title, url, description, saved_at FROM saved_job WHERE user_id=:u ORDER BY saved_at DESC LIMIT {limit}")
        , {"u": user_id}).fetchall()
    return [{"title": r[0], "url": r[1], "description": r[2], "saved_at": r[3]} for r in rows]
