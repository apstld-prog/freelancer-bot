import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

engine = create_engine(DATABASE_URL, future=True)

with engine.begin() as conn:
    print("🔧 Checking foreign key in saved_job...")
    # Drop old FK constraint if it exists
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'saved_job_user_id_fkey'
            ) THEN
                ALTER TABLE saved_job DROP CONSTRAINT saved_job_user_id_fkey;
            END IF;
        END$$;
    """))

    # Recreate correct FK → users(id)
    conn.execute(text("""
        ALTER TABLE saved_job
        ADD CONSTRAINT saved_job_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE;
    """))

print("✅ Migration completed — saved_job now references users(id)")
