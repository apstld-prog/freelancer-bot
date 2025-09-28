# db.py
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

logging.basicConfig(level=logging.INFO, format="%(asctime)s [db] %(levelname)s: %(message)s")
logger = logging.getLogger("db")

# ---------- Engine / Session ----------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")

# SQLite needs check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

UTC = timezone.utc
def now_utc():
    return datetime.now(UTC)

# ---------- Models ----------
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(64), unique=True, index=True, nullable=False)

    trial_until = Column(DateTime(timezone=True), nullable=True)
    access_until = Column(DateTime(timezone=True), nullable=True)
    is_blocked = Column(Boolean, default=False)

    countries = Column(String(128), default="ALL")
    proposal_template = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    keyword = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)

class JobSaved(Base):
    __tablename__ = "job_saved"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(256), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_user_job"),)

class JobDismissed(Base):
    __tablename__ = "job_dismissed"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(256), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_dismissed_user_job"),)

class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(256), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_sent_user_job"),)

# ---------- Schema helper ----------
def ensure_schema() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("DB schema ensured.")
