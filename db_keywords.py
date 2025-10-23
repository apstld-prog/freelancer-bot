# db_keywords.py — handles tables with columns (keyword, value), timestamps, and unique indexes
from typing import List, Tuple, Dict, Any
from sqlalchemy import text
from db import get_session

_CACHE: Dict[str, Any] = {"cols": None, "nulls": None, "has_created": None, "has_updated": None}

def _detect_cols(conn) -> Tuple[bool, bool]:
    """Return (has_keyword, has_value) for table keyword."""
    if _CACHE["cols"] is not None:
        return _CACHE["cols"]  # type: ignore
    rows = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='keyword' AND column_name IN ('keyword','value')
    """)).fetchall()
    names = {r[0] for r in rows}
    _CACHE["cols"] = ("keyword" in names, "value" in names)
    return _CACHE["cols"]  # type: ignore

def _detect_nullability(conn) -> Tuple[bool, bool]:
    """Return (value_not_null, keyword_not_null)."""
    if _CACHE["nulls"] is not None:
        return _CACHE["nulls"]  # type: ignore
    rows = conn.execute(text("""
        SELECT column_name, is_nullable
        FROM information_schema.columns
        WHERE table_name='keyword' AND column_name IN ('keyword','value')
    """)).fetchall()
    nn = {r[0]: (r[1] == "NO") for r in rows}
    _CACHE["nulls"] = (nn.get("value", False), nn.get("keyword", False))
    return _CACHE["nulls"]  # type: ignore

def _detect_ts_cols(conn):
    if _CACHE["has_created"] is not None:
        return _CACHE["has_created"], _CACHE["has_updated"]
    rows = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='keyword' AND column_name IN ('created_at','updated_at')
    """)).fetchall()
    names = {r[0] for r in rows}
    _CACHE["has_created"] = "created_at" in names
    _CACHE["has_updated"] = "updated_at" in names
    return _CACHE["has_created"], _CACHE["has_updated"]

def ensure_keyword_unique():
    with get_session() as s:
        conn = s.connection()
        has_kw, has_val = _detect_cols(conn)
        if has_kw:
            s.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_keyword_user_keyword ON keyword (user_id, keyword)"))
        if has_val:
            s.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_keyword_user_value   ON keyword (user_id, value)"))
        s.commit()

def list_keywords(user_id: int) -> List[str]:
    with get_session() as s:
        has_kw, has_val = _detect_cols(s.connection())
        if has_kw and has_val:
            q = "SELECT COALESCE(keyword, value) AS k FROM keyword WHERE user_id=:uid ORDER BY id"
        elif has_kw:
            q = "SELECT keyword AS k FROM keyword WHERE user_id=:uid ORDER BY id"
        else:
            q = "SELECT value AS k FROM keyword WHERE user_id=:uid ORDER BY id"
        rows = s.execute(text(q), {"uid": user_id}).fetchall()
        return [r[0] for r in rows]

def count_keywords(user_id: int) -> int:
    with get_session() as s:
        return int(s.execute(text("SELECT COUNT(*) FROM keyword WHERE user_id=:uid"), {"uid": user_id}).scalar() or 0)

def add_keywords(user_id: int, kws: List[str]) -> int:
    if not kws: return 0
    inserted = 0
    with get_session() as s:
        conn = s.connection()
        has_kw, has_val = _detect_cols(conn)
        val_nn, kw_nn = _detect_nullability(conn)
        has_created, has_updated = _detect_ts_cols(conn)

        # Στήλες που θα βάλουμε
        cols = ["user_id"]
        vals = [":uid"]

        # Αν υπάρχουν και οι δύο στήλες, γράφουμε και στις δύο με την ίδια τιμή.
        if has_kw:
            cols.append("keyword"); vals.append(":kw")
        if has_val:
            cols.append("value");   vals.append(":kw")

        if has_created:
            cols.append("created_at"); vals.append("NOW() AT TIME ZONE 'UTC'")
        if has_updated:
            cols.append("updated_at"); vals.append("NOW() AT TIME ZONE 'UTC'")

        sql = f"INSERT INTO keyword ({', '.join(cols)}) VALUES ({', '.join(vals)}) ON CONFLICT DO NOTHING"

        for kw in kws:
            res = s.execute(text(sql), {"uid": user_id, "kw": kw})
            if getattr(res, "rowcount", 0) == 1:
                inserted += 1
        s.commit()
    return inserted

def delete_keywords(user_id: int, kws: List[str]) -> int:
    if not kws: return 0
    with get_session() as s:
        conn = s.connection()
        has_kw, has_val = _detect_cols(conn)
        if has_kw and has_val:
            cond = "(keyword = ANY(:kws) OR value = ANY(:kws))"
        elif has_kw:
            cond = "keyword = ANY(:kws)"
        else:
            cond = "value = ANY(:kws)"
        res = s.execute(text(f"DELETE FROM keyword WHERE user_id=:uid AND {cond}"), {"uid": user_id, "kws": kws})
        s.commit()
        return int(getattr(res, "rowcount", 0))

def clear_keywords(user_id: int) -> int:
    with get_session() as s:
        res = s.execute(text("DELETE FROM keyword WHERE user_id=:uid"), {"uid": user_id})
        s.commit()
        return int(getattr(res, "rowcount", 0))
