# db.py
import os
import logging
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column, Integer, String, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.engine import Engine
from sqlalchemy import inspect

log = logging.getLogger("db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [db] %(levelname)s: %(message)s")

# -----------------------------------------------------------------------------
# Engine / Session
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    # fallback σε τοπικό SQLite (μόνο για dev). Στο Render βάλε Postgres!
    DATABASE_URL = "sqlite:///./freelancer.db"

# SQLAlchemy engine
engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()

UTC = timezone.utc
def now_utc():
    return datetime.now(UTC)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(64), unique=True, index=True, nullable=False)

    trial_until = Column(DateTime(timezone=True), nullable=True)
    access_until = Column(DateTime(timezone=True), nullable=True)

    is_blocked = Column(Boolean, nullable=False, default=False)

    countries = Column(String(64), nullable=True)               # π.χ. "ALL" ή "GR,UK"
    proposal_template = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")
    sent_jobs = relationship("JobSent", back_populates="user", cascade="all, delete-orphan")
    saved_jobs = relationship("SavedJob", back_populates="user", cascade="all, delete-orphan")


class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    user = relationship("User", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),
    )


class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String(128), nullable=False)  # e.g. freelancer-39847081
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    user = relationship("User", back_populates="sent_jobs")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_usersent_job"),
    )


class SavedJob(Base):
    __tablename__ = "saved_job"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String(128), nullable=False)  # e.g. freelancer-39847081
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    user = relationship("User", back_populates="saved_jobs")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_saved_job"),
    )

# -----------------------------------------------------------------------------
# Schema management
# -----------------------------------------------------------------------------
def ensure_schema() -> None:
    """
    Δημιουργεί *μόνο* ό,τι λείπει. Δεν επιχειρεί να ξαναφτιάξει πίνακες/constraints.
    Αποφεύγουμε raw DDL για να μην ξαναπέσουμε σε DuplicateTable / DuplicateConstraint.
    """
    insp = inspect(engine)

    # Αν δεν υπάρχει καν ο πίνακας user, τότε κανένα schema δεν έχει φτιαχτεί. Κάνε create_all.
    if not insp.has_table("user"):
        Base.metadata.create_all(bind=engine, checkfirst=True)
        log.info("DB schema ensured (fresh create).")
        return

    # Αλλιώς, απλώς βεβαιώσου ότι όλα υπάρχουν (idempotent).
    Base.metadata.create_all(bind=engine, checkfirst=True)
    log.info("DB schema ensured.")

# -----------------------------------------------------------------------------
# Helper για FastAPI/Workers
# -----------------------------------------------------------------------------
__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "ensure_schema",
    "User",
    "Keyword",
    "JobSent",
    "SavedJob",
    "now_utc",
]
