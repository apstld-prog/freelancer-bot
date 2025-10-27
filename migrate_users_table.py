import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

engine = create_engine(DATABASE_URL, future=True)

commands = [
    # Add missing columns if not exist
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE;",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_until TIMESTAMP WITH TIME ZONE;",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS access_until TIMESTAMP WITH TIME ZONE;"
]

with engine.begin() as conn:
    for cmd in commands:
        print(f"Applying: {cmd}")
        conn.execute(text(cmd))

print("✅ Migration completed successfully.")
