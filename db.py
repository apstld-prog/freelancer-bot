import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, TIMESTAMP,
    ForeignKey, UniqueConstraint, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)

    # flags
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_blocked = Column(Boolean, nullable=False, server_default=text("false"))

    # access dates
    trial_start = Column(TIMESTAMP(timezone=True))
    trial_end = Column(TIMESTAMP(timezone=True))
    license_until = Column(TIMESTAMP(timezone=True))

    # settings
    countries = Column(String)                 # CSV or 'ALL'
    proposal_template = Column(String)

    # audit
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


def ensure_schema():
    # 1) create tables if not exist
    Base.metadata.create_all(bind=engine)

    # 2) idempotent migrations: add missing columns safely
    with engine.begin() as conn:
        # user flags
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='is_active') THEN
                ALTER TABLE "user" ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='is_blocked') THEN
                ALTER TABLE "user" ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT false;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='is_admin') THEN
                ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false;
            END IF;
        END $$;""")

        # user access dates
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='trial_start') THEN
                ALTER TABLE "user" ADD COLUMN trial_start TIMESTAMPTZ NULL;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='trial_end') THEN
                ALTER TABLE "user" ADD COLUMN trial_end TIMESTAMPTZ NULL;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='license_until') THEN
                ALTER TABLE "user" ADD COLUMN license_until TIMESTAMPTZ NULL;
            END IF;
        END $$;""")

        # user settings
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='countries') THEN
                ALTER TABLE "user" ADD COLUMN countries TEXT NULL;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='proposal_template') THEN
                ALTER TABLE "user" ADD COLUMN proposal_template TEXT NULL;
            END IF;
        END $$;""")

        # user audit
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='created_at') THEN
                ALTER TABLE "user" ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='updated_at') THEN
                ALTER TABLE "user" ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;
        END $$;""")

        # keyword audit
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='keyword' AND column_name='created_at') THEN
                ALTER TABLE keyword ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='keyword' AND column_name='updated_at') THEN
                ALTER TABLE keyword ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;
        END $$;""")


def init_db():
    ensure_schema()
