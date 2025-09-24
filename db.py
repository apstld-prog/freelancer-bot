import os
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DB_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    countries = Column(String, nullable=True)

class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    keyword = Column(String)
    user = relationship("User")
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)

class JobSent(Base):
    __tablename__ = "jobs_sent"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    job_id = Column(String)
    user = relationship("User")
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_jobsent"),)

class SavedJob(Base):
    __tablename__ = "saved_jobs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    job_id = Column(String)
    user = relationship("User")
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_savedjob"),)

Base.metadata.create_all(engine)
