import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# -------------------------------------------------------------------
# Database connection
# -------------------------------------------------------------------
# Use DATABASE_URL from environment; fallback to local SQLite for dev.
# Examples:
#   postgres://user:pass@host:5432/dbname
#   postgresql+psycopg2://user:pass@host:5432/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./freelancer_bot.db")

# Render/Heroku commonly need this for pooled connections; echo=False for clean logs
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def utcnow() -> datetime:
    """UTC timestamp helper."""
    return datetime.now(timezone.utc)


# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------
class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)

    # We store telegram_id as STRING for portability (and to avoid bigint issues).
    telegram_id = Column(String(32), unique=True, index=True, nullable=False)

    # Access control
    trial_until = Column(DateTime(timezone=True), nullable=True)
    access_until = Column(DateTime(timezone=True), nullable=True)
    is_blocked = Column(Boolean, default=False, nullable=False)

    # Preferences
    countries = Column(String(64), default="ALL", nullable=True)
    proposal_template = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")
    saved_jobs = relationship("JobSaved", back_populates="user", cascade="all, delete-orphan")
    dismissed_jobs = relationship("JobDismissed", back_populates="user", cascade="all, delete-orphan")
    sent_jobs = relationship("JobSent", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id}>"


class Keyword(Base):
    __tablename__ = "keyword"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    keyword = Column(String(100), index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),
    )

    def __repr__(self) -> str:
        return f"<Keyword user_id={self.user_id} kw='{self.keyword}'>"


class JobSent(Base):
    """
    Marker of messages already delivered to a user.
    NOTE: We keep only user_id & job_id as agreed. No 'sent_at' column required.
    """
    __tablename__ = "job_sent"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(255), nullable=False)  # e.g. "freelancer-123456" / "fiverr-logo-20240922"

    user = relationship("User", back_populates="sent_jobs")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_sent_user_job"),
        Index("ix_job_sent_job_id", "job_id"),
    )

    def __repr__(self) -> str:
        return f"<JobSent user_id={self.user_id} job_id='{self.job_id}'>"


class JobSaved(Base):
    """Jobs the user chose to keep (⭐ Keep)."""
    __tablename__ = "job_saved"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(255), nullable=False)
    saved_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="saved_jobs")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_saved_user_job"),
        Index("ix_job_saved_job_id", "job_id"),
    )

    def __repr__(self) -> str:
        return f"<JobSaved user_id={self.user_id} job_id='{self.job_id}'>"


class JobDismissed(Base):
    """Jobs the user deleted (🗑 Delete)."""
    __tablename__ = "job_dismissed"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(255), nullable=False)
    dismissed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="dismissed_jobs")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_dismissed_user_job"),
        Index("ix_job_dismissed_job_id", "job_id"),
    )

    def __repr__(self) -> str:
        return f"<JobDismissed user_id={self.user_id} job_id='{self.job_id}'>"


# -------------------------------------------------------------------
# Create tables on import (simple bootstrap). In production you may
# want Alembic migrations; but this keeps Render/first-run simple.
# -------------------------------------------------------------------
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


# Ensure tables exist when module is imported.
init_db()
