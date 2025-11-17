# db_keywords.py – fully compatible with bot.py
import datetime
from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, UniqueConstraint, text
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),)

def ensure_keyword_unique():
    return  # handled by table constraint

def list_keywords(user_id: int) -> list[str]:
    from db import get_session
    with get_session() as s:
        rows = s.execute(text("SELECT value FROM keyword WHERE user_id=:u"), {"u": user_id}).fetchall()
    return [r[0] for r in rows]

def add_keywords(user_id: int, values: list[str]) -> int:
    from db import get_session
    cleaned = []
    for v in values:
        v = v.strip().lower()
        if v:
            cleaned.append(v)
    inserted = 0
    with get_session() as s:
        for v in cleaned:
            exists = s.execute(
                text("SELECT 1 FROM keyword WHERE user_id=:u AND value=:v"),
                {"u": user_id, "v": v}
            ).fetchone()
            if exists:
                continue
            s.execute(
                text("INSERT INTO keyword (user_id, value) VALUES (:u, :v)"),
                {"u": user_id, "v": v}
            )
            inserted += 1
        s.commit()
    return inserted

def delete_keywords(user_id: int, values: list[str]) -> int:
    from db import get_session
    cleaned = [v.strip().lower() for v in values if v.strip()]
    removed = 0
    with get_session() as s:
        for v in cleaned:
            r = s.execute(
                text("DELETE FROM keyword WHERE user_id=:u AND value=:v RETURNING id"),
                {"u": user_id, "v": v}
            ).fetchone()
            if r:
                removed += 1
        s.commit()
    return removed

def clear_keywords(user_id: int) -> int:
    from db import get_session
    with get_session() as s:
        rows = s.execute(
            text("DELETE FROM keyword WHERE user_id=:u RETURNING id"),
            {"u": user_id}
        ).fetchall()
        s.commit()
    return len(rows)

def count_keywords(user_id: int) -> int:
    from db import get_session
    with get_session() as s:
        c = s.execute(
            text("SELECT COUNT(*) FROM keyword WHERE user_id=:u"),
            {"u": user_id}
        ).scalar()
    return int(c or 0)
