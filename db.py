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
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_blocked = Column(Boolean, nullable=False, server_default=text("false"))
    countries = Column(String)
    proposal_template = Column(String)
    trial_end = Column(TIMESTAMP(timezone=True))
    license_until = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    keywords = relationship("Keyword", back_populates="user", cascade="all, delete")


class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"))
    value = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    user = relationship("User", back_populates="keywords")
    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),)


def ensure_schema():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='user' AND column_name='is_active'
            ) THEN
                ALTER TABLE "user" ADD COLUMN is_active BOOLEAN DEFAULT true;
            END IF;
        END $$;
        """)


def init_db():
    ensure_schema()
