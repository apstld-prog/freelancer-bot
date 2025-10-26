import os, sys
sys.path.append(os.path.dirname(__file__))
from db import session
from db_keywords import Keyword

DEFAULT_KEYWORDS = ["logo", "lighting", "dialux", "relux", "led", "φωτισμός", "luminaire"]

def ensure_keywords():
    existing = [k.keyword for k in session.query(Keyword).all()]
    missing = [k for k in DEFAULT_KEYWORDS if k not in existing]

    if missing:
        print(f"🔄 Inserting missing keywords: {missing}")
        for kw in missing:
            session.add(Keyword(keyword=kw))
        session.commit()
        print("✅ Default keywords inserted.")
    else:
        print("✅ All default keywords already exist.")

if __name__ == "__main__":
    ensure_keywords()
