import os
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, DateTime, Float,
    ForeignKey, UniqueConstraint, Index, func
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

log = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

# -----------------
# MODELS
# -----------------

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    is_admin = Column(Boolean, nullable=False, server_default="false")  # <— ΝΕΟ
    is_active = Column(Boolean, nullable=False, server_default="true")
    is_blocked = Column(Boolean, nullable=False, server_default="false")

    trial_start = Column(DateTime(timezone=True))
    trial_end = Column(DateTime(timezone=True))
    license_until = Column(DateTime(timezone=True))
    countries = Column(String)                 # π.χ. "ALL" ή "US,UK"
    proposal_template = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    keywords = relationship("Keyword", back_populates="user", cascade="all,delete-orphan")
    saved = relationship("SavedJob", back_populates="user", cascade="all,delete-orphan")


class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    value = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())   # <— ΝΕΟ
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())  # <— ΝΕΟ

    user = relationship("User", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),
        Index("ix_keyword_user", "user_id"),
    )


class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True)

    # Πηγή + ID από την πηγή (μοναδικός συνδυασμός)
    source = Column(String, nullable=False)            # π.χ. "Freelancer", "Skywalker"
    source_id = Column(String, nullable=False)         # π.χ. "39861162"
    external_id = Column(String)                       # optional, παλαιό πεδίο

    title = Column(Text)
    description = Column(Text)
    url = Column(Text)
    proposal_url = Column(Text)
    original_url = Column(Text)

    budget_min = Column(Float)
    budget_max = Column(Float)
    budget_currency = Column(String)                   # "USD", "EUR", κλπ
    job_type = Column(String)
    bids_count = Column(Integer)

    matched_keyword = Column(String)
    posted_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_source_source_id"),
        Index("ix_job_source", "source"),
    )


class SavedJob(Base):
    __tablename__ = "saved_job"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="saved")
    job = relationship("Job")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_saved_job_user_job"),
        Index("ix_saved_user", "user_id"),
    )


class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_sent_user_job"),
        Index("ix_jobsent_user", "user_id"),
    )

# -----------------
# INIT / MIGRATIONS
# -----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    """Δημιουργεί πίνακες & εκτελεί ασφαλείς ‘μικρο-μεταναστεύσεις’ (IF NOT EXISTS)."""
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # User.is_admin (αν λείπει)
        conn.exec_driver_sql("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='user' AND column_name='is_admin'
                ) THEN
                    ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false;
                END IF;
            END $$;
        """)

        # Keyword.created_at / updated_at (αν λείπουν)
        conn.exec_driver_sql("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='keyword' AND column_name='created_at'
                ) THEN
                    ALTER TABLE keyword ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='keyword' AND column_name='updated_at'
                ) THEN
                    ALTER TABLE keyword ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
                END IF;
            END $$;
        """)

        # Unique index για job (source, source_id)
        conn.exec_driver_sql("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes WHERE indexname = 'uq_job_source_source_id'
                ) THEN
                    CREATE UNIQUE INDEX uq_job_source_source_id
                    ON job (source, source_id);
                END IF;
            END $$;
        """)

    log.info("DB schema ensured.")


def init_db():
    if not engine:
        raise RuntimeError("DATABASE_URL is not configured")
    ensure_schema()
    return engine
