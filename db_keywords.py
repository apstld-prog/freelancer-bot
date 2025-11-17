# db_keywords.py patched
import datetime
from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()

class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),)

def add_keyword(session: Session, user_id: int, value: str):
    value = value.strip().lower()
    if not value:
        return False
    existing = session.query(Keyword).filter_by(user_id=user_id, value=value).first()
    if existing:
        return True
    k = Keyword(user_id=user_id, value=value)
    session.add(k)
    session.commit()
    return True

def delete_keyword(session: Session, user_id: int, value: str):
    value = value.strip().lower()
    q = session.query(Keyword).filter_by(user_id=user_id, value=value)
    if q.first():
        q.delete()
        session.commit()
        return True
    return False

def list_keywords(session: Session, user_id: int):
    return [k.value for k in session.query(Keyword).filter_by(user_id=user_id).all()]
