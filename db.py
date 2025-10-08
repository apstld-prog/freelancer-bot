# db.py
# -*- coding: utf-8 -*-
import os
import logging
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Text, Float, UniqueConstraint, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

log = logging.getLogger("db")
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
UTC = timezone.utc

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None
Base = declarative_base()

# --- Models you already had (kept same names/columns) ---
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(64), unique=True, index=True, nullable=False)
    started_at = Column(DateTime(timezone=True))
    trial_until = Column(DateTime(timezone=True))
    access_until = Column(DateTime(timezone=True))   # aka license_until
    is_blocked = Column(Boolean, default=False)

    # relationships (optional)
    keywords = relationship("Keyword", back_populates="user", lazy="selectin")

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), index=True)
    keyword = Column(String(256), index=True)
    user = relationship("User", back_populates="keywords")

class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True)
    source = Column(String(64), index=True, nullable=False)
    source_id = Column(String(64), index=True, nullable=False)
    external_id = Column(String(128))
    title = Column(String(512), nullable=False)
    description = Column(Text)
    url = Column(Text, nullable=False)
    proposal_url = Column(Text)
    original_url = Column(Text)
    budget_min = Column(Float)
    budget_max = Column(Float)
    budget_currency = Column(String(16))
    job_type = Column(String(32))
    bids_count = Column(Integer)
    matched_keyword = Column(String(256))
    posted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_source_sourceid"),
        Index("ix_job_posted_at", "posted_at"),
    )

class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    job_id = Column(Integer, ForeignKey("job.id"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

# NEW: actions per user/job (save/delete)
class JobAction(Base):
    __tablename__ = "job_action"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    job_id = Column(Integer, ForeignKey("job.id"), index=True, nullable=False)
    action = Column(String(16), nullable=False)  # "save" | "delete"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_job_action_user_job", "user_id", "job_id", "action", unique=True),)

def init_db():
    if not engine:
        log.warning("No DB engine configured.")
        return
    Base.metadata.create_all(engine)
    log.info("DB schema ensured.")
