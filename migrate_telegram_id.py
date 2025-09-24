# migrate_telegram_id.py
from sqlalchemy import create_engine, text
import os

def main():
    db_url = os.environ.get("DB_URL")
    if not db_url:
        raise RuntimeError("DB_URL not set in environment")

    engine = create_engine(db_url)

    with engine.begin() as conn:
        print("Running migration: change telegram_id to BIGINT...")
        conn.execute(text("ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT"))
        print("Migration complete ✅")

if __name__ == "__main__":
    main()
