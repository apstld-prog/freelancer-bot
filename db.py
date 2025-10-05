import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, UniqueConstraint, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("db")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL") or "sqlite:///freelancer.db"
# Render/Heroku style: sometimes needs postgresql+psycopg2
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DB_URL.startswith("postgresql://") and "+psycopg2" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

@contextmanager
def get_session():
    """Context-managed session that always closes properly."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(32), nullable=False, unique=True)  # store as text
    started_at = Column(DateTime(timezone=True), nullable=True)
    trial_until = Column(DateTime(timezone=True), nullable=True)
    access_until = Column(DateTime(timezone=True), nullable=True)
    is_blocked = Column(Boolean, nullable=False, default=False)

    name = Column(String(128), nullable=True)
    username = Column(String(64), nullable=True)

    countries = Column(String(256), nullable=False, default="ALL")
    proposal_template = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")
    saved_jobs = relationship("SavedJob", back_populates="user", cascade="all, delete-orphan")

    def is_active(self) -> bool:
        if self.is_blocked:
            return False
        now = now_utc()
        # Active if within trial or has license
        if (self.trial_until and self.trial_until >= now) or (self.access_until and self.access_until >= now):
            return True
        return False


class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)


class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True)
    # origin/source
    source = Column(String(64), nullable=False)           # e.g., freelancer, fiverr, pph, kariera
    source_id = Column(String(128), nullable=True)        # remote id/hash

    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)

    url = Column(Text, nullable=False)                    # canonical job url
    proposal_url = Column(Text, nullable=True)            # affiliate-wrapped proposal url
    original_url = Column(Text, nullable=True)            # original url (may be same as url)

    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    budget_currency = Column(String(16), nullable=True)   # USD, EUR, etc.
    job_type = Column(String(32), nullable=True)          # fixed/hourly if known
    bids_count = Column(Integer, nullable=True)

    matched_keyword = Column(String(256), nullable=True)  # last matched kw for display
    posted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_source_sid"),)


class SavedJob(Base):
    __tablename__ = "saved_job"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

    user = relationship("User", back_populates="saved_jobs")


class ContactThread(Base):
    __tablename__ = "contact_thread"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    is_open = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)


# ---------------------------------------------------------------------------
# Schema ensure / migrations-light
# ---------------------------------------------------------------------------
def _safe_alter_columns(conn):
    """
    Add new columns safely if they don't exist (PostgreSQL / SQLite friendly).
    Only idempotent ALTERs here.
    """
    dialect = conn.engine.dialect.name

    # --- USER table columns that may be missing on older schemas ---
    # PostgreSQL supports IF NOT EXISTS. SQLite supports it for ADD COLUMN since 3.35.
    alter_stmts = [
        # user table fields
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS name VARCHAR(128)",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS username VARCHAR(64)",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS countries VARCHAR(256) DEFAULT 'ALL'",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS proposal_template TEXT",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT (NOW())",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT (NOW())",

        # saved_job table (in case it's missing)
        "CREATE TABLE IF NOT EXISTS saved_job ("
        "   id SERIAL PRIMARY KEY,"
        "   user_id INTEGER NOT NULL REFERENCES \"user\"(id) ON DELETE CASCADE,"
        "   job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,"
        "   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")",
        # contact_thread table (in case it's missing)
        "CREATE TABLE IF NOT EXISTS contact_thread ("
        "   id SERIAL PRIMARY KEY,"
        "   user_id INTEGER NOT NULL REFERENCES \"user\"(id) ON DELETE CASCADE,"
        "   is_open BOOLEAN NOT NULL DEFAULT TRUE,"
        "   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")",
    ]

    # SQLite compatibility tweaks
    if dialect == "sqlite":
        # Replace TIMESTAMPTZ with TIMESTAMP for SQLite
        def sqlite_normalize(sql):
            return (sql.replace("TIMESTAMPTZ", "TIMESTAMP")
                       .replace("NOW()", "(datetime('now'))")
                       .replace("SERIAL", "INTEGER"))
        alter_stmts = [sqlite_normalize(s) for s in alter_stmts]

    for stmt in alter_stmts:
        try:
            conn.execute(text(stmt))
        except Exception as e:
            # Be tolerant: IF NOT EXISTS should be safe; log any edge errors and continue.
            log.debug("Skip/ignore on migration stmt: %s -> %s", stmt, e)


def init_db():
    """Create base tables and then apply idempotent column alters."""
    # 1) Create base tables by metadata (no IF NOT EXISTS needed; SQLAlchemy is idempotent)
    Base.metadata.create_all(bind=engine)
    # 2) Run idempotent ALTERs to add missing columns/aux tables
    with engine.begin() as conn:
        _safe_alter_columns(conn)
    log.info("DB schema ensured.")


# ---------------------------------------------------------------------------
# Admin bootstrap
# ---------------------------------------------------------------------------
def ensure_admin(session, admin_telegram_id: str | None):
    """
    Ensure the ADMIN user exists (by telegram_id). No-op if ADMIN not configured.
    """
    if not admin_telegram_id:
        return
    u = session.query(User).filter(User.telegram_id == str(admin_telegram_id)).one_or_none()
    if not u:
        u = User(
            telegram_id=str(admin_telegram_id),
            started_at=now_utc(),
            trial_until=now_utc(),  # admin doesn't rely on trial
            access_until=now_utc(), # will be treated as inactive but admin rights checked by ID
            is_blocked=False,
            name="Admin",
            username=None,
            countries="ALL",
        )
        session.add(u)
        session.commit()
    else:
        # keep it updated with sane defaults
        changed = False
        if u.name is None:
            u.name = "Admin"; changed = True
        if u.countries is None:
            u.countries = "ALL"; changed = True
        if changed:
            session.commit()
