
-- db_migrate_telegram_id_bigint.sql
-- Converts "user".telegram_id from text/varchar to BIGINT on Postgres.
-- Idempotent-ish: checks type before altering.
DO $$
DECLARE
  col_type text;
BEGIN
  SELECT data_type INTO col_type
  FROM information_schema.columns
  WHERE table_name = 'user' AND column_name = 'telegram_id';
  IF col_type <> 'bigint' THEN
    -- Ensure all values are numeric before casting
    -- If any non-numeric rows exist, this will raise. Inspect first if needed.
    ALTER TABLE "user"
      ALTER COLUMN telegram_id TYPE BIGINT USING telegram_id::bigint;
    CREATE UNIQUE INDEX IF NOT EXISTS ix_user_telegram_id ON "user"(telegram_id);
  END IF;
END$$;
