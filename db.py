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
# DB URL normalize
# ---------------------------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL") or "sqlite:///freelancer.db"
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
    telegram_id = Column(String(32), nullable=False, unique=True)  # keep as text
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

    source = Column(String(64), nullable=False)            # freelancer, pph, kariera, etc.
    source_id = Column(String(128), nullable=True)         # remote id/hash

    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)

    url = Column(Text, nullable=False)                     # canonical job url
    proposal_url = Column(Text, nullable=True)             # affiliate-wrapped
    original_url = Column(Text, nullable=True)             # original

    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    budget_currency = Column(String(16), nullable=True)    # USD, EUR, etc.
    job_type = Column(String(32), nullable=True)           # fixed/hourly
    bids_count = Column(Integer, nullable=True)

    matched_keyword = Column(String(256), nullable=True)   # last matched kw for display
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
    """
    Anti-duplication log: what job was already sent to which user (for X time).
    """
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

# ---------------------------------------------------------------------------
# Schema ensure / light migration
# ---------------------------------------------------------------------------
def _pg_column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return bool(row)

def _safe_alter_columns(conn):
    dialect = conn.engine.dialect.name

    if dialect == "postgresql":
        # Add missing columns on "user"
        if not _pg_column_exists(conn, "user", "started_at"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN started_at TIMESTAMPTZ'))
        if not _pg_column_exists(conn, "user", "name"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN name VARCHAR(128)'))
        if not _pg_column_exists(conn, "user", "username"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN username VARCHAR(64)'))
        if not _pg_column_exists(conn, "user", "countries"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN countries VARCHAR(256) DEFAULT \'ALL\''))
        if not _pg_column_exists(conn, "user", "proposal_template"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN proposal_template TEXT'))
        if not _pg_column_exists(conn, "user", "created_at"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()'))
        if not _pg_column_exists(conn, "user", "updated_at"):
            conn.execute(text('ALTER TABLE "user" ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW()'))

        # Ensure aux tables exist (CREATE IF NOT EXISTS)
        conn.execute(text(
            'CREATE TABLE IF NOT EXISTS saved_job ('
            '  id SERIAL PRIMARY KEY,'
            '  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,'
            '  job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,'
            '  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ')'
        ))
        conn.execute(text(
            'CREATE TABLE IF NOT EXISTS job_sent ('
            '  id SERIAL PRIMARY KEY,'
            '  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,'
            '  job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,'
            '  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '  CONSTRAINT uq_job_sent_user_job UNIQUE (user_id, job_id)'
            ')'
        ))
        conn.execute(text(
            'CREATE TABLE IF NOT EXISTS contact_thread ('
            '  id SERIAL PRIMARY KEY,'
            '  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,'
            '  is_open BOOLEAN NOT NULL DEFAULT TRUE,'
            '  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()'
            ')'
        ))

    else:
        # SQLite-compatible fallbacks
        def norm(sql: str) -> str:
            return (sql.replace("TIMESTAMPTZ", "TIMESTAMP")
                       .replace("NOW()", "(datetime('now'))")
                       .replace("SERIAL", "INTEGER"))
        stmts = [
            'ALTER TABLE "user" ADD COLUMN started_at TIMESTAMP',
            'ALTER TABLE "user" ADD COLUMN name VARCHAR(128)',
            'ALTER TABLE "user" ADD COLUMN username VARCHAR(64)',
            'ALTER TABLE "user" ADD COLUMN countries VARCHAR(256) DEFAULT \'ALL\'',
            'ALTER TABLE "user" ADD COLUMN proposal_template TEXT',
            'ALTER TABLE "user" ADD COLUMN created_at TIMESTAMP DEFAULT (datetime(\'now\'))',
            'ALTER TABLE "user" ADD COLUMN updated_at TIMESTAMP DEFAULT (datetime(\'now\'))',
            'CREATE TABLE IF NOT EXISTS saved_job ('
            '  id INTEGER PRIMARY KEY,'
            '  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,'
            '  job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,'
            '  created_at TIMESTAMP NOT NULL DEFAULT (datetime(\'now\'))'
            ')',
            'CREATE TABLE IF NOT EXISTS job_sent ('
            '  id INTEGER PRIMARY KEY,'
            '  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,'
            '  job_id INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,'
            '  created_at TIMESTAMP NOT NULL DEFAULT (datetime(\'now\')),'
            '  CONSTRAINT uq_job_sent_user_job UNIQUE (user_id, job_id)'
            ')',
            'CREATE TABLE IF NOT EXISTS contact_thread ('
            '  id INTEGER PRIMARY KEY,'
            '  user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,'
            '  is_open BOOLEAN NOT NULL DEFAULT 1,'
            '  created_at TIMESTAMP NOT NULL DEFAULT (datetime(\'now\'))'
            ')',
        ]
        for s in stmts:
            try:
                conn.execute(text(norm(s)))
            except Exception:
                pass

def init_db():
    # 1) Create base tables
    Base.metadata.create_all(bind=engine)
    # 2) Apply idempotent alters/creates
    with engine.begin() as conn:
        _safe_alter_columns(conn)
    log.info("DB schema ensured.")

# ---------------------------------------------------------------------------
# Admin bootstrap
# ---------------------------------------------------------------------------
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
