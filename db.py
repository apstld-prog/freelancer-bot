import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, text, Numeric
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

def now_utc():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_blocked = Column(Boolean, nullable=False, server_default=text("false"))
    trial_start = Column(TIMESTAMP(timezone=True))
    trial_end = Column(TIMESTAMP(timezone=True))
    license_until = Column(TIMESTAMP(timezone=True))
    countries = Column(String)
    proposal_template = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    value = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),)

class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    external_id = Column(String)
    title = Column(String, nullable=False)
    description = Column(String)
    url = Column(String)
    proposal_url = Column(String)
    original_url = Column(String)
    budget_min = Column(Numeric(12,2))
    budget_max = Column(Numeric(12,2))
    budget_currency = Column(String)
    job_type = Column(String)
    bids_count = Column(Integer)
    matched_keyword = Column(String)
    posted_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_job_source_sourceid"),)

class JobSent(Base):
    __tablename__ = "job_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_jobsent_user_job"),)

class SavedJob(Base):
    __tablename__ = "saved_job"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_user_job"),)

def ensure_schema():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN NOT NULL DEFAULT false;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin   BOOLEAN NOT NULL DEFAULT false;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS trial_start TIMESTAMPTZ NULL;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS trial_end   TIMESTAMPTZ NULL;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS license_until TIMESTAMPTZ NULL;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS countries TEXT NULL;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS proposal_template TEXT NULL;')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();')
        conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();')

        conn.exec_driver_sql('ALTER TABLE keyword ADD COLUMN IF NOT EXISTS value TEXT NULL;')
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='keyword' AND column_name='keyword') THEN
                UPDATE keyword SET value = COALESCE(value, keyword) WHERE value IS NULL OR value='';
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='keyword' AND column_name='name') THEN
                UPDATE keyword SET value = COALESCE(value, name) WHERE value IS NULL OR value='';
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='keyword' AND column_name='term') THEN
                UPDATE keyword SET value = COALESCE(value, term) WHERE value IS NULL OR value='';
            END IF;
            UPDATE keyword SET value='' WHERE value IS NULL;
        END $$;
        """)
        conn.exec_driver_sql('ALTER TABLE keyword ALTER COLUMN value SET NOT NULL;')

        conn.exec_driver_sql("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_keyword_user_value') THEN
                ALTER TABLE keyword ADD CONSTRAINT uq_keyword_user_value UNIQUE (user_id, value);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_job_source_sourceid') THEN
                ALTER TABLE job ADD CONSTRAINT uq_job_source_sourceid UNIQUE (source, source_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_jobsent_user_job') THEN
                ALTER TABLE job_sent ADD CONSTRAINT uq_jobsent_user_job UNIQUE (user_id, job_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_saved_user_job') THEN
                ALTER TABLE saved_job ADD CONSTRAINT uq_saved_user_job UNIQUE (user_id, job_id);
            END IF;
        END $$;""")

def init_db():
    ensure_schema()
