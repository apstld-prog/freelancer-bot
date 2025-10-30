# db_keywords.py
# Psycopg2-only, complete API expected by bot.py & workers
# Includes delete_keywords() alias for delete_user_keyword()

from typing import Dict, List, Iterable, Optional
from db import get_session


def _normalize_keywords(value: Iterable[str] | str) -> List[str]:
    items: List[str] = []
    if isinstance(value, str):
        for part in (
            value.replace("\n", ",").replace(";", ",").replace("|", ",")
        ).split(","):
            k = part.strip().lower()
            if k:
                items.append(k)
    else:
        for part in value:
            k = (part or "").strip().lower()
            if k:
                items.append(k)
    seen = set()
    out: List[str] = []
    for k in items:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def ensure_keyword_unique() -> None:
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS user_keywords (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            keyword TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname='ux_user_keywords_user_id_keyword'
            ) THEN
                CREATE UNIQUE INDEX ux_user_keywords_user_id_keyword
                ON user_keywords(user_id, keyword);
            END IF;
        END$$;
        """)
        # de-dup legacy
        s.execute("""
        DELETE FROM user_keywords a
        USING user_keywords b
        WHERE a.id < b.id AND a.user_id=b.user_id AND a.keyword=b.keyword;
        """)
        s.commit()


def add_user_keyword(user_id: int, keyword: str) -> None:
    add_keywords(user_id, [keyword])


def add_keywords(user_id: int, keywords: str | Iterable[str]) -> None:
    kws = _normalize_keywords(keywords)
    if not kws:
        return
    with get_session() as s:
        for k in kws:
            s.execute(
                "INSERT INTO user_keywords (user_id, keyword) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (user_id, k),
            )
        s.commit()


def delete_user_keyword(user_id: int, keyword: str) -> None:
    kws = _normalize_keywords(keyword)
    if not kws:
        return
    with get_session() as s:
        for k in kws:
            s.execute("DELETE FROM user_keywords WHERE user_id=%s AND keyword=%s;", (user_id, k))
        s.commit()


# 🔧 new alias required by bot.py
def delete_keywords(user_id: int, keywords: str | Iterable[str]) -> None:
    """Alias for delete_user_keyword() — used by bot.py"""
    delete_user_keyword(user_id, keywords)


def clear_user_keywords(user_id: int) -> None:
    with get_session() as s:
        s.execute("DELETE FROM user_keywords WHERE user_id=%s;", (user_id,))
        s.commit()


def get_user_keywords(user_id: int) -> List[str]:
    with get_session() as s:
        s.execute("SELECT keyword FROM user_keywords WHERE user_id=%s ORDER BY keyword ASC;", (user_id,))
        rows = s.fetchall()
        return [r["keyword"] for r in rows]


def list_keywords(user_id: Optional[int] = None) -> List[str]:
    with get_session() as s:
        if user_id is None:
            s.execute("SELECT DISTINCT keyword FROM user_keywords ORDER BY keyword ASC;")
        else:
            s.execute("SELECT DISTINCT keyword FROM user_keywords WHERE user_id=%s ORDER BY keyword ASC;", (user_id,))
        rows = s.fetchall()
        return [r["keyword"] for r in rows]


def get_all_user_keywords() -> Dict[int, List[str]]:
    with get_session() as s:
        s.execute("SELECT user_id, keyword FROM user_keywords ORDER BY user_id, keyword;")
        rows = s.fetchall()
    out: Dict[int, List[str]] = {}
    for r in rows:
        uid = int(r["user_id"])
        out.setdefault(uid, []).append(r["keyword"])
    return out


def count_keywords(user_id: Optional[int] = None) -> int:
    with get_session() as s:
        if user_id is None:
            s.execute("SELECT COUNT(*) AS c FROM user_keywords;")
        else:
            s.execute("SELECT COUNT(*) AS c FROM user_keywords WHERE user_id=%s;", (user_id,))
        row = s.fetchone()
        return int(row["c"]) if row else 0


def ensure_keywords() -> None:
    # default for admin (id=1)
    add_keywords(1, ["logo", "lighting", "design", "sales"])


if __name__ == "__main__":
    print("======================================================")
    print("🔑 INIT KEYWORDS TOOL — psycopg2 version (FINAL-FINAL)")
    print("======================================================")
    ensure_keyword_unique()
    ensure_keywords()
    print("✅ Default keywords ensured successfully.")
    print("======================================================")
