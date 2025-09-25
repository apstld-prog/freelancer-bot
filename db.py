import os
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    ForeignKey,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# --------------------------------------------------------------------
# Database URL
# Example:
#   postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME
# --------------------------------------------------------------------
DB_URL = os.getenv("DB_URL") or os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DB_URL (or DATABASE_URL) is not set in environment variables.")

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# --------------------------------------------------------------------
# Models
# --------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    # Telegram can exceed INT range, so use BIGINT
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    countries = Column(String(255), nullable=True)           # e.g. "US,UK" or "ALL"
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
    job_id = Column(String(255), nullable=False)

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


# --------------------------------------------------------------------
# Auto create tables (idempotent)
# --------------------------------------------------------------------
def init_db():
    Base.metadata.create_all(bind=engine)

# Initialize on import
init_db()
