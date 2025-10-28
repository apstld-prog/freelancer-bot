import os
import logging
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, Text, Boolean,
    TIMESTAMP, ForeignKey, text, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

log = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

def now_utc():
    return datetime.now(timezone.utc)

# ======================================================
# MODELS
# ======================================================

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_blocked = Column(Boolean, nullable=False, server_default=text("false"))
    countries = Column(Text, nullable=True)
    proposal_template = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),)

# ======================================================
# SCHEMA / MIGRATIONS
# ======================================================

def _safe_exec(session, sql: str):
    try:
        session.execute(text(sql))
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        log.warning("migrate skip: %s", e)
        return False

def ensure_schema():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        _safe_exec(s, """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='keyword' AND column_name='value'
            ) THEN
                ALTER TABLE keyword ADD COLUMN value TEXT NULL;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='keyword' AND column_name='keyword'
            ) THEN
                UPDATE keyword SET value = COALESCE(value, keyword) WHERE value IS NULL OR value='';
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='keyword' AND column_name='name'
            ) THEN
                UPDATE keyword SET value = COALESCE(value, name) WHERE value IS NULL OR value='';
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='keyword' AND column_name='term'
            ) THEN
                UPDATE keyword SET value = COALESCE(value, term) WHERE value IS NULL OR value='';
            END IF;

            UPDATE keyword SET value = '' WHERE value IS NULL;
            ALTER TABLE keyword ALTER COLUMN value SET NOT NULL;
        END $$;
        """)
        _safe_exec(s, """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = 'uq_keyword_user_value'
            ) THEN
                CREATE UNIQUE INDEX uq_keyword_user_value
                    ON keyword(user_id, value);
            END IF;
        END $$;
        """)

# ======================================================
# HELPERS
# ======================================================

def get_session():
    return SessionLocal()

def get_or_create_user_by_tid(db, telegram_id: int) -> User:
    u = db.query(User).filter(User.telegram_id == telegram_id).one_or_none()
    if u:
        return u
    u = User(telegram_id=telegram_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def list_user_keywords(db, user_id: int) -> list[str]:
    rows = db.query(Keyword).filter(Keyword.user_id == user_id).order_by(Keyword.id.asc()).all()
    return [r.value for r in rows]

def add_user_keywords(db, user_id: int, keywords: list[str]) -> int:
    if not keywords:
        return 0
    normalized, seen = [], set()
    for k in keywords:
        v = (k or "").strip().lower()
        if not v or v in seen:
            continue
        seen.add(v)
        normalized.append(v)
    existing = {k.value for k in db.query(Keyword).filter(
        Keyword.user_id == user_id,
        Keyword.value.in_(normalized)
    ).all()}
    to_insert = [v for v in normalized if v not in existing]
    for v in to_insert:
        db.add(Keyword(user_id=user_id, value=v))
    if to_insert:
        db.commit()
    return len(to_insert)

# ======================================================
# get_user_keywords — fixed for “value” column
# ======================================================
def get_user_keywords():
    """Return {telegram_id: [keywords]} for all active users (reads value column)."""
    result = {}
    try:
        with get_session() as s:
            tables = [r[0] for r in s.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
            ).fetchall()]
            table = "users" if "users" in tables else "user"
            sql = f"""
                SELECT u.telegram_id, k.value
                FROM {table} AS u
                LEFT JOIN keyword AS k ON k.user_id = u.id
                WHERE u.is_active = TRUE OR u.is_admin = TRUE
                ORDER BY u.telegram_id
            """
            rows = s.execute(text(sql)).fetchall()
            for tid, kw in rows:
                if not tid:
                    continue
                result.setdefault(int(tid), [])
                if kw and kw not in result[tid]:
                    result[tid].append(kw)
        print(f"[get_user_keywords] ✅ Loaded keywords for {len(result)} users")
    except Exception as e:
        print(f"[get_user_keywords] ❌ Error: {e}")
    return result
