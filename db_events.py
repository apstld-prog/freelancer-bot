
from datetime import datetime, timedelta
from typing import Dict
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DATABASE_URL, STATS_WINDOW_HOURS

Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class FeedEvent(Base):
    __tablename__ = "feed_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), index=True, nullable=False)
    ts = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)

def ensure_schema():
    Base.metadata.create_all(engine)

def log_platform_event(source: str):
    with SessionLocal() as s:
        s.add(FeedEvent(source=source, ts=datetime.utcnow()))
        s.commit()

def get_platform_stats(hours: int = STATS_WINDOW_HOURS) -> Dict[str, int]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    with SessionLocal() as s:
        rows = s.query(FeedEvent.source).filter(FeedEvent.ts >= cutoff).all()
    counts: Dict[str, int] = {}
    for (src,) in rows:
        counts[src] = counts.get(src, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[0]))
