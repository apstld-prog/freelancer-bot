import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

log = logging.getLogger("db")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./freelancer.db")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

# --- Models -----------------------------------------------------------------

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(32), index=True, unique=True, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    trial_until = Column(DateTime(timezone=True), nullable=True)
    access_until = Column(DateTime(timezone=True), nullable=True)
    is_blocked = Column(Boolean, default=False, nullable=False)

    name = Column(String(128), nullable=True)
    username = Column(String(64), nullable=True)

    countries = Column(String(128), default="ALL", nullable=False)
    proposal_template = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    keywords = relationship("Keyword", back_populates="user", cascade="all,delete-orphan")
    saved = relationship("SavedJob", back_populates="user", cascade="all,delete-orphan")

    def is_active(self) -> bool:
        now = now_utc()
        return bool(
            (self.trial_until and self.trial_until >= now) or
            (self.access_until and self.access_until >= now)
        ) and not self.is_blocked

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)

    user = relationship("User", back_populates="keywords")

class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True)
    source = Column(String(64), nullable=False)          # freelancer / pph / kariera / ...
    external_id = Column(String(128), nullable=False)    # e.g. 39851269
    title = Column(String(512), nullable=False)
    url = Column(Text, nullable=False)
    proposal_url = Column(Text, nullable=True)           # affiliate-wrapped if any
    original_url = Column(Text, nullable=True)           # original/affiliate-wrapped same-domain
    budget_min = Column(Integer, nullable=True)
    budget_max = Column(Integer, nullable=True)
    budget_currency = Column(String(8), nullable=True)
    bids = Column(Integer, nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    description = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_xid"),)

class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job"),)

class SavedJob(Base):
    __tablename__ = "saved_job"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_saved_job"),)

    user = relationship("User", back_populates="saved")

class ContactThread(Base):
    __tablename__ = "contact_thread"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    is_open = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    last_msg_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

# --- helpers ----------------------------------------------------------------

def init_db():
    Base.metadata.create_all(bind=engine)
    log.info("DB schema ensured.")

def get_session() -> Session:
    return SessionLocal()

# --- bootstrap admin --------------------------------------------------------

def ensure_admin(session: Session, admin_id: Optional[str]):
    if not admin_id:
        return
    u = session.query(User).filter(User.telegram_id == str(admin_id)).one_or_none()
    if not u:
        u = User(
            telegram_id=str(admin_id),
            name="ADMIN",
            started_at=now_utc(),
            trial_until=now_utc() + timedelta(days=3650),
            access_until=now_utc() + timedelta(days=3650),
            is_blocked=False,
        )
        session.add(u)
        session.commit()
        log.info("Seeded admin user %s", admin_id)
