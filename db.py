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

# ---------------------------------------------------------
# MODELS
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# SCHEMA MANAGEMENT
# ---------------------------------------------------------
def ensure_schema():
    log.info("Ensuring DB schema...")
    Base.metadata.create_all(bind=engine)
    log.info("✅ Schema check complete.")

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
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
    normalized = []
    seen = set()
    for k in keywords:
        v = (k or "").strip().lower()
        if not v or v in seen:
            continue
        seen.add(v)
        normalized.append(v)
    if not normalized:
        return 0
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

# ---------------------------------------------------------
# LEGACY COMPATIBILITY (for worker_runner)
# ---------------------------------------------------------
def get_connection():
    """Return a raw DB connection for legacy worker_runner code."""
    return engine.raw_connection()
