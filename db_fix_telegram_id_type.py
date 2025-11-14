
# db_fix_telegram_id_type.py
# Usage:
#   set DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:PORT/DBNAME
#   python db_fix_telegram_id_type.py
import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("[ERROR] DATABASE_URL env var is missing.")
    sys.exit(1)

engine = create_engine(DATABASE_URL, future=True)

SQL = '''
DO $$
DECLARE
  col_type text;
BEGIN
  SELECT data_type INTO col_type
  FROM information_schema.columns
  WHERE table_name = 'user' AND column_name = 'telegram_id';
  IF col_type <> 'bigint' THEN
    ALTER TABLE "user"
      ALTER COLUMN telegram_id TYPE BIGINT USING telegram_id::bigint;
    CREATE UNIQUE INDEX IF NOT EXISTS ix_user_telegram_id ON "user"(telegram_id);
  END IF;
END$$;
'''

with engine.begin() as conn:
    conn.execute(text(SQL))

print("[OK] telegram_id column ensured to be BIGINT.")
