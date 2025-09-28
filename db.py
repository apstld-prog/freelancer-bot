import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./freelancer_bot.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(32), unique=True, index=True, nullable=False)
    trial_until = Column(DateTime(timezone=True), nullable=True)
    access_until = Column(DateTime(timezone=True), nullable=True)
    is_blocked = Column(Boolean, default=False, nullable=False)
    countries = Column(String(64), default="ALL", nullable=True)
    proposal_template = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")
    saved_jobs = relationship("JobSaved", back_populates="user", cascade="all, delete-orphan")
    dismissed_jobs = relationship("JobDismissed", back_populates="user", cascade="all, delete-orphan")
    sent_jobs = relationship("JobSent", back_populates="user", cascade="all, delete-orphan")

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    keyword = Column(String(100), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)

class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)
    job_id = Column(String(255), nullable=False)
    user = relationship("User", back_populates="sent_jobs")
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_sent_user_job"),
        Index("ix_job_sent_job_id", "job_id"),
    )

class JobSaved(Base):
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

class JobDismissed(Base):
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

def init_db():
    Base.metadata.create_all(bind=engine)
