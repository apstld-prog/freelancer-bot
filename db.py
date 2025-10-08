# db.py
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    Float,
    func,
    text,
    UniqueConstraint,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("db")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
# Περιμένουμε το DATABASE_URL από το περιβάλλον (Render).
import os

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # τοπικό fallback (προαιρετικό)
    DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ---------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------
class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False, index=True)

    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_blocked = Column(Boolean, default=False, nullable=False)

    trial_start = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    license_until = Column(DateTime(timezone=True), nullable=True)

    countries = Column(String, nullable=True)         # π.χ. "ALL" ή "US,UK"
    proposal_template = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Keyword(Base):
    __tablename__ = "keyword"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    term = Column(String, nullable=False, index=True)

    # >>> προσθήκη timestamps ώστε το /addkeyword να δέχεται created_at <<<
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "term", name="uq_keyword_user_term"),
    )


class Job(Base):
    __tablename__ = "job"

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False, index=True)          # π.χ. "Freelancer"
    source_id = Column(String, nullable=False, index=True)       # το id στη πλατφόρμα
    external_id = Column(String, nullable=True)                   # optional stable id

    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    proposal_url = Column(Text, nullable=True)
    original_url = Column(Text, nullable=True)

    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    budget_currency = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    bids_count = Column(Integer, nullable=True)

    matched_keyword = Column(String, nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_source_sourceid"),
    )


class JobSent(Base):
    __tablename__ = "job_sent"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    job_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SavedJob(Base):
    __tablename__ = "saved_job"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    job_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminMessage(Base):
    __tablename__ = "admin_message"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    admin_id = Column(Integer, nullable=False, index=True)
    direction = Column(String, nullable=False)  # 'user_to_admin' | 'admin_to_user'
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# ---------------------------------------------------------------------
# Schema ensure / lightweight migrations
# ---------------------------------------------------------------------
def _column_exists(table: str, column: str) -> bool:
    sql = text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
        LIMIT 1
    """)
    with engine.connect() as conn:
        res = conn.execute(sql, {"t": table, "c": column}).first()
        return bool(res)

def _safe_exec(sql_stmt: str, log_ok: str):
    with engine.begin() as conn:
        try:
            conn.execute(text(sql_stmt))
            logger.info("migrate ok: %s", log_ok)
        except (ProgrammingError, OperationalError) as e:
            # αν υπάρχει ήδη/ασυμβατότητα, το αγνοούμε
            logger.warning("migrate skip (%s): %s", log_ok, e)

def ensure_schema() -> None:
    """Δημιουργεί πίνακες & εφαρμόζει μικρο-migrations αν λείπουν στήλες."""
    Base.metadata.create_all(bind=engine)

    # --- Keyword.created_at / updated_at ---
    if not _column_exists("keyword", "created_at"):
        _safe_exec(
            "ALTER TABLE keyword ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();",
            "keyword.created_at"
        )
    if not _column_exists("keyword", "updated_at"):
        _safe_exec(
            "ALTER TABLE keyword ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();",
            "keyword.updated_at"
        )

    # --- Job unique index ασφάλεια (αν δεν υπάρχει ήδη) ---
    _safe_exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_job_source_sourceid_idx ON job (source, source_id);",
        "job uq(source,source_id) index"
    )

    logger.info("DB schema ensured.")

# Καλείται από server/worker στην εκκίνηση
ensure_schema()
