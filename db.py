import os
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, ForeignKey, UniqueConstraint, create_engine, DateTime, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

DB_URL = os.getenv("DB_URL") or os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DB_URL (or DATABASE_URL) is not set in environment variables.")

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    countries = Column(String(255), nullable=True)
    proposal_template = Column(Text, nullable=True)
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
    job_id = Column(String(255), nullable=False)   # source-specific id OR fingerprint
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

# NEW: global dedup fingerprints
class JobFingerprint(Base):
    __tablename__ = "job_fingerprints"
    id = Column(Integer, primary_key=True)
    # stable fingerprint across sources (e.g., normalized title+desc hash)
    fingerprint = Column(String(64), unique=True, nullable=False)
    # canonical URL we prefer to send (ideally from affiliate-enabled source)
    canonical_url = Column(Text, nullable=False)
    source = Column(String(50), nullable=False)  # e.g., 'freelancer','malt','pph'
    title = Column(Text, nullable=True)
    country = Column(String(10), nullable=True)
    has_affiliate = Column(Boolean, default=False, nullable=False)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

def init_db():
    Base.metadata.create_all(bind=engine)

init_db()
