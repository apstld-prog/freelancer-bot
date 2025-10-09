# db_keywords.py — resilient access to keyword table (column can be `keyword` or `value`)
from typing import List
from sqlalchemy import text
from db import get_session

_CACHE = {"col": None}

def _detect_col(conn) -> str:
    """Detect if table `keyword` uses column `keyword` or `value`."""
    if _CACHE["col"]:
        return _CACHE["col"]  # type: ignore
    q = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='keyword' AND column_name IN ('keyword','value')
        ORDER BY CASE column_name WHEN 'keyword' THEN 0 ELSE 1 END
        LIMIT 1
    """)
    col = conn.execute(q).scalar()
    if not col:
        col = "keyword"
    _CACHE["col"] = str(col)
    return _CACHE["col"]  # type: ignore

def ensure_keyword_unique():
    """Create unique index on (user_id, <col>) if missing. Safe to call at startup."""
    with get_session() as s:
        col = _detect_col(s.connection())
        s.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_keyword_user_{col} ON keyword (user_id, {col})"))
        s.commit()

def list_keywords(user_id: int) -> List[str]:
    with get_session() as s:
        col = _detect_col(s.connection())
        rows = s.execute(
            text(f"SELECT {col} FROM keyword WHERE user_id=:uid ORDER BY id"),
            {"uid": user_id}
        ).fetchall()
        return [r[0] for r in rows]

def count_keywords(user_id: int) -> int:
    with get_session() as s:
        return int(s.execute(text("SELECT COUNT(*) FROM keyword WHERE user_id=:uid"), {"uid": user_id}).scalar() or 0)

def add_keywords(user_id: int, kws: List[str]) -> int:
    if not kws:
        return 0
    inserted = 0
    with get_session() as s:
        col = _detect_col(s.connection())
        ins = text(f"INSERT INTO keyword (user_id, {col}) VALUES (:uid, :kw) ON CONFLICT DO NOTHING")
        for kw in kws:
            res = s.execute(ins, {"uid": user_id, "kw": kw})
            if getattr(res, "rowcount", 0) == 1:
                inserted += 1
        s.commit()
    return inserted

def delete_keywords(user_id: int, kws: List[str]) -> int:
    """Delete specific keywords. Returns number of rows affected."""
    if not kws:
        return 0
    with get_session() as s:
        col = _detect_col(s.connection())
        q = text(f"DELETE FROM keyword WHERE user_id=:uid AND {col} = ANY(:kws)")
        res = s.execute(q, {"uid": user_id, "kws": kws})
        s.commit()
        return int(getattr(res, "rowcount", 0))

def clear_keywords(user_id: int) -> int:
    """Delete all keywords for a user."""
    with get_session() as s:
        res = s.execute(text("DELETE FROM keyword WHERE user_id=:uid"), {"uid": user_id})
        s.commit()
        return int(getattr(res, "rowcount", 0))
