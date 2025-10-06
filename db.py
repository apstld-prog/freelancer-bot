import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, UniqueConstraint, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("db")

# -----------------------------------------------------------------------------
# DB URL normalize
# -----------------------------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL") or "sqlite:///freelancer.db"
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DB_URL.startswith("postgresql://") and "+psycopg2" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc)

@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(32), nullable=False, unique=True)   # store as text for safety
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
        return bool(
            (self.trial_until and self.trial_until >= now) or
            (self.access_until and self.access_until >= now)
        )

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

    source = Column(String(64), nullable=False)              # freelancer, pph, kariera, etc.
    source_id = Column(String(128), nullable=True)           # remote id/hash (νέο)
    external_id = Column(String(128), nullable=True)         # legacy id

    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)

    url = Column(Text, nullable=False)                       # canonical job url
    proposal_url = Column(Text, nullable=True)               # affiliate-wrapped
    original_url = Column(Text, nullable=True)               # original

    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    budget_currency = Column(String(16), nullable=True)      # USD, EUR, etc.
    job_type = Column(String(32), nullable=True)             # fixed/hourly
    bids_count = Column(Integer, nullable=True)

    matched_keyword = Column(String(256), nullable=True)     # last matched kw for display
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

class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_job_sent_user_job"),)

class ContactThread(Base):
    __tablename__ = "contact_thread"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    is_open = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)

# -----------------------------------------------------------------------------
# Light migrations (idempotent)
# -----------------------------------------------------------------------------
def _pg_column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return bool(row)

def _pg_col_type(conn, table: str, column: str) -> str | None:
    row = conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row[0] if row else None

def _safe_alter_user(conn):
    if conn.engine.dialect.name == "postgresql":
        def add(colsql: str): conn.execute(text(colsql))
        if not _pg_column_exists(conn, "user", "started_at"):
            add('ALTER TABLE "user" ADD COLUMN started_at TIMESTAMPTZ')
        if not _pg_column_exists(conn, "user", "name"):
            add('ALTER TABLE "user" ADD COLUMN name VARCHAR(128)')
        if not _pg_column_exists(conn, "user", "username"):
            add('ALTER TABLE "user" ADD COLUMN username VARCHAR(64)')
        if not _pg_column_exists(conn, "user", "countries"):
            add('ALTER TABLE "user" ADD COLUMN countries VARCHAR(256) DEFAULT \'ALL\'')
        if not _pg_column_exists(conn, "user", "proposal_template"):
            add('ALTER TABLE "user" ADD COLUMN proposal_template TEXT')
        if not _pg_column_exists(conn, "user", "created_at"):
            add('ALTER TABLE "user" ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()')
        if not _pg_column_exists(conn, "user", "updated_at"):
            add('ALTER TABLE "user" ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW()')
    else:
        stmts = [
            'ALTER TABLE "user" ADD COLUMN started_at TIMESTAMP',
            'ALTER TABLE "user" ADD COLUMN name VARCHAR(128)',
            'ALTER TABLE "user" ADD COLUMN username VARCHAR(64)',
            'ALTER TABLE "user" ADD COLUMN countries VARCHAR(256) DEFAULT \'ALL\'',
            'ALTER TABLE "user" ADD COLUMN proposal_template TEXT',
            'ALTER TABLE "user" ADD COLUMN created_at TIMESTAMP DEFAULT (datetime(\'now\'))',
            'ALTER TABLE "user" ADD COLUMN updated_at TIMESTAMP DEFAULT (datetime(\'now\'))',
        ]
        for s in stmts:
            try: conn.execute(text(s))
            except Exception: pass

def _safe_alter_job(conn):
    pg = conn.engine.dialect.name == "postgresql"
    def add(colsql: str): conn.execute(text(colsql))

    if pg:
        if not _pg_column_exists(conn, "job", "source_id"):
            add('ALTER TABLE job ADD COLUMN source_id VARCHAR(128)')
        if not _pg_column_exists(conn, "job", "external_id"):
            add('ALTER TABLE job ADD COLUMN external_id VARCHAR(128)')
        else:
            conn.execute(text("ALTER TABLE job ALTER COLUMN external_id DROP NOT NULL"))
        if not _pg_column_exists(conn, "job", "proposal_url"):
            add('ALTER TABLE job ADD COLUMN proposal_url TEXT')
        if not _pg_column_exists(conn, "job", "original_url"):
            add('ALTER TABLE job ADD COLUMN original_url TEXT')
        if not _pg_column_exists(conn, "job", "budget_min"):
            add('ALTER TABLE job ADD COLUMN budget_min DOUBLE PRECISION')
        if not _pg_column_exists(conn, "job", "budget_max"):
            add('ALTER TABLE job ADD COLUMN budget_max DOUBLE PRECISION')
        if not _pg_column_exists(conn, "job", "budget_currency"):
            add('ALTER TABLE job ADD COLUMN budget_currency VARCHAR(16)')
        if not _pg_column_exists(conn, "job", "job_type"):
            add('ALTER TABLE job ADD COLUMN job_type VARCHAR(32)')
        if not _pg_column_exists(conn, "job", "bids_count"):
            add('ALTER TABLE job ADD COLUMN bids_count INTEGER')
        if not _pg_column_exists(conn, "job", "matched_keyword"):
            add('ALTER TABLE job ADD COLUMN matched_keyword VARCHAR(256)')
        if not _pg_column_exists(conn, "job", "posted_at"):
            add('ALTER TABLE job ADD COLUMN posted_at TIMESTAMPTZ')
        if not _pg_column_exists(conn, "job", "created_at"):
            add('ALTER TABLE job ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()')
        if not _pg_column_exists(conn, "job", "updated_at"):
            add('ALTER TABLE job ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW()')

        # Backfill external_id from source_id
        conn.execute(text("UPDATE job SET external_id = source_id WHERE external_id IS NULL AND source_id IS NOT NULL"))

        # Unique index
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_job_source_sid ON job(source, source_id)'))
    else:
        stmts = [
            'ALTER TABLE job ADD COLUMN source_id VARCHAR(128)',
            'ALTER TABLE job ADD COLUMN external_id VARCHAR(128)',
            'ALTER TABLE job ADD COLUMN proposal_url TEXT',
            'ALTER TABLE job ADD COLUMN original_url TEXT',
            'ALTER TABLE job ADD COLUMN budget_min FLOAT',
            'ALTER TABLE job ADD COLUMN budget_max FLOAT',
            'ALTER TABLE job ADD COLUMN budget_currency VARCHAR(16)',
            'ALTER TABLE job ADD COLUMN job_type VARCHAR(32)',
            'ALTER TABLE job ADD COLUMN bids_count INTEGER',
            'ALTER TABLE job ADD COLUMN matched_keyword VARCHAR(256)',
            'ALTER TABLE job ADD COLUMN posted_at TIMESTAMP',
            'ALTER TABLE job ADD COLUMN created_at TIMESTAMP DEFAULT (datetime(\'now\'))',
            'ALTER TABLE job ADD COLUMN updated_at TIMESTAMP DEFAULT (datetime(\'now\'))',
        ]
        for s in stmts:
            try: conn.execute(text(s))
            except Exception: pass
        try:
            conn.execute(text("UPDATE job SET external_id = source_id WHERE external_id IS NULL AND source_id IS NOT NULL"))
        except Exception:
            pass
        try:
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_job_source_sid ON job(source, source_id)'))
        except Exception:
            pass

def _safe_alter_link_tables(conn):
    """Normalize types for job_sent.* and saved_job.* to INTEGER in Postgres."""
    if conn.engine.dialect.name != "postgresql":
        return

    def ensure_integer(table: str, column: str):
        if not _pg_column_exists(conn, table, column):
            return
        dt = _pg_col_type(conn, table, column)  # e.g. 'character varying', 'integer'
        if dt and dt != "integer":
            # Cast to integer if possible
            conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE INTEGER USING {column}::integer'))

    # job_sent normalization
    ensure_integer("job_sent", "user_id")
    ensure_integer("job_sent", "job_id")
    # saved_job normalization
    ensure_integer("saved_job", "user_id")
    ensure_integer("saved_job", "job_id")

def init_db():
    # 1) Create base tables by metadata
    Base.metadata.create_all(bind=engine)
    # 2) Add missing columns / indexes idempotently
    with engine.begin() as conn:
        _safe_alter_user(conn)
        _safe_alter_job(conn)
        _safe_alter_link_tables(conn)
    log.info("DB schema ensured.")

# -----------------------------------------------------------------------------
# Admin bootstrap
# -----------------------------------------------------------------------------
def ensure_admin(session, admin_telegram_id: str | None):
    if not admin_telegram_id:
        return
    u = session.query(User).filter(User.telegram_id == str(admin_telegram_id)).one_or_none()
    if not u:
        u = User(
            telegram_id=str(admin_telegram_id),
            started_at=now_utc(),
            trial_until=now_utc(),
            access_until=now_utc(),
            is_blocked=False,
            name="Admin",
            username=None,
            countries="ALL",
        )
        session.add(u)
        session.commit()
    else:
        changed = False
        if u.name is None:
            u.name = "Admin"; changed = True
        if u.countries is None:
            u.countries = "ALL"; changed = True
        if changed:
            session.commit()
