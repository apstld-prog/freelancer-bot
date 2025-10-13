
from typing import List, Dict, Optional
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
import hashlib, json

def ensure_saved_schema():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS saved_job (
                id BIGSERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                job_key TEXT,
                title TEXT,
                url TEXT,
                description TEXT,
                data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """))
        s.execute(_sql_text("CREATE INDEX IF NOT EXISTS idx_saved_job_chat ON saved_job(chat_id);"))
        s.execute(_sql_text("CREATE UNIQUE INDEX IF NOT EXISTS uq_saved_job_chat_jobkey ON saved_job(chat_id, job_key);"))
        s.commit()

def _make_key(title: str, url: str) -> str:
    src = (url or "") or (title or "")
    return hashlib.sha1(src.encode("utf-8", errors="ignore")).hexdigest()

def add_saved_job(user_id: int, title: str, url: str, description: str = "", data: Optional[Dict]=None):
    ensure_saved_schema()
    key = _make_key(title, url)
    payload = json.dumps(data or {}, ensure_ascii=False)
    with _get_session() as s:
        s.execute(_sql_text("""
            INSERT INTO saved_job (chat_id, job_key, title, url, description, data)
            VALUES (:u, :k, :t, :url, :d, CAST(:js AS JSONB))
            ON CONFLICT (chat_id, job_key) DO UPDATE SET
                title=EXCLUDED.title,
                url=EXCLUDED.url,
                description=EXCLUDED.description,
                data=EXCLUDED.data
        """), {"u": user_id, "k": key, "t": title or "", "url": url or "", "d": description or "", "js": payload})
        s.commit()

def list_saved_jobs(user_id: int, limit: int = 20) -> List[Dict]:
    ensure_saved_schema()
    with _get_session() as s:
        rows = s.execute(_sql_text("""
            SELECT title, url, description, created_at
            FROM saved_job WHERE chat_id=:u
            ORDER BY created_at DESC LIMIT :lim
        """), {"u": user_id, "lim": limit}).fetchall()
    out = []
    for t, u, d, c in rows:
        out.append({"title": t or u or "(no title)", "url": u or "", "description": d or "", "created_at": c})
    return out
