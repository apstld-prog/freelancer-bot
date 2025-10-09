# db_keywords.py — robust insert: handles (keyword|value) + created_at/updated_at NOT NULL
from typing import List, Tuple
from sqlalchemy import text
from db import get_session

_CACHE = {"col": None, "has_created": None, "has_updated": None}

def _detect_col(conn) -> str:
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

def _detect_ts_cols(conn) -> Tuple[bool, bool]:
    """Return (has_created_at, has_updated_at) for table keyword."""
    if _CACHE["has_created"] is not None and _CACHE["has_updated"] is not None:
        return bool(_CACHE["has_created"]), bool(_CACHE["has_updated"])  # type: ignore
    rows = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='keyword' AND column_name IN ('created_at','updated_at')
    """)).fetchall()
    names = {r[0] for r in rows}
    _CACHE["has_created"] = "created_at" in names
    _CACHE["has_updated"] = "updated_at" in names
    return bool(_CACHE["has_created"]), bool(_CACHE["has_updated"])  # type: ignore

def ensure_keyword_unique():
    """Create unique index on (user_id, <col>) if missing. Safe to call at startup."""
    with get_session() as s:
        col = _detect_col(s.connection())
        s.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_keyword_user_{col} ON keyword (user_id, {col})"))
        s.commit()

def list_keywords(user_id: int) -> List[str]:
    with get_session() as s:
        col = _detect_col(s.connection())
        rows = s.execute(text(f"SELECT {col} FROM keyword WHERE user_id=:uid ORDER BY id"),
                         {"uid": user_id}).fetchall()
        return [r[0] for r in rows]

def count_keywords(user_id: int) -> int:
    with get_session() as s:
        return int(s.execute(text("SELECT COUNT(*) FROM keyword WHERE user_id=:uid"), {"uid": user_id}).scalar() or 0)

def add_keywords(user_id: int, kws: List[str]) -> int:
    """Insert keywords with safe timestamps if required; returns how many νέες εγγραφές μπήκαν."""
    if not kws:
        return 0
    inserted = 0
    with get_session() as s:
        conn = s.connection()
        col = _detect_col(conn)
        has_created, has_updated = _detect_ts_cols(conn)

        # Build INSERT … (user_id, <col>, [created_at], [updated_at]) VALUES …
        cols = ["user_id", col]
        vals = [":uid", ":kw"]
        params_common = {"uid": user_id}

        if has_created:
            cols.append("created_at")
            vals.append("NOW() AT TIME ZONE 'UTC'")
        if has_updated:
            cols.append("updated_at")
            vals.append("NOW() AT TIME ZONE 'UTC'")

        sql = f"INSERT INTO keyword ({', '.join(cols)}) VALUES ({', '.join(vals)}) ON CONFLICT DO NOTHING"

        for kw in kws:
            params = dict(params_common)
            params["kw"] = kw
            res = s.execute(text(sql), params)
            if getattr(res, "rowcount", 0) == 1:
                inserted += 1
        s.commit()
    return inserted

def delete_keywords(user_id: int, kws: List[str]) -> int:
    if not kws:
        return 0
    with get_session() as s:
        col = _detect_col(s.connection())
        res = s.execute(text(f"DELETE FROM keyword WHERE user_id=:uid AND {col} = ANY(:kws)"),
                        {"uid": user_id, "kws": kws})
        s.commit()
        return int(getattr(res, "rowcount", 0))

def clear_keywords(user_id: int) -> int:
    with get_session() as s:
        res = s.execute(text("DELETE FROM keyword WHERE user_id=:uid"), {"uid": user_id})
        s.commit()
        return int(getattr(res, "rowcount", 0))
