import os
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, ForeignKey, UniqueConstraint,
    create_engine, DateTime, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func, text

DB_URL = os.getenv("DB_URL") or os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DB_URL (or DATABASE_URL) is not set in env.")

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    countries = Column(String(255), nullable=True)
    proposal_template = Column(Text, nullable=True)

    # Access control
    started_at = Column(DateTime(timezone=True), nullable=True)   # first /start
    trial_until = Column(DateTime(timezone=True), nullable=True)  # free trial expiry
    access_until = Column(DateTime(timezone=True), nullable=True) # paid/approved access expiry
    is_blocked = Column(Boolean, default=False, nullable=False)

    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")

class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(255), nullable=False)
    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)

class JobSent(Base):
    __tablename__ = "jobs_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    job_id = Column(String(255), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_sent"),)

class JobSaved(Base):
    __tablename__ = "jobs_saved"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    job_id = Column(String(255), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_saved"),)

class JobDismissed(Base):
    __tablename__ = "jobs_dismissed"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    job_id = Column(String(255), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_dismissed"),)

class JobFingerprint(Base):
    __tablename__ = "job_fingerprints"
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String(64), unique=True, nullable=False)
    canonical_url = Column(Text, nullable=False)
    source = Column(String(50), nullable=False)
    title = Column(Text, nullable=True)
    country = Column(String(10), nullable=True)
    has_affiliate = Column(Boolean, default=False, nullable=False)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class AppLock(Base):
    __tablename__ = "app_locks"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

def init_db():
    # create tables if not exist
    Base.metadata.create_all(bind=engine)
    # add columns if they don’t exist (Postgres-safe)
    with engine.begin() as conn:
        conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='users' AND column_name='started_at') THEN
                ALTER TABLE users ADD COLUMN started_at TIMESTAMPTZ NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='users' AND column_name='trial_until') THEN
                ALTER TABLE users ADD COLUMN trial_until TIMESTAMPTZ NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='users' AND column_name='access_until') THEN
                ALTER TABLE users ADD COLUMN access_until TIMESTAMPTZ NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='users' AND column_name='is_blocked') THEN
                ALTER TABLE users ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END$$;
        """))

init_db()
