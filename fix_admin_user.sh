
#!/usr/bin/env bash
set -euo pipefail

echo "===================================================="
echo "🔧 AUTO-FIX: ADMIN USER IN POSTGRES DATABASE"
echo "===================================================="
echo

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "❌ DATABASE_URL not set"
  exit 1
fi

echo "👉 Connecting to PostgreSQL..."

psql "$DATABASE_URL" <<'SQL'
-- Ensure modern table
CREATE TABLE IF NOT EXISTS "user" (
  id            INTEGER PRIMARY KEY,
  telegram_id   BIGINT,
  username      TEXT,
  is_admin      BOOLEAN DEFAULT FALSE NOT NULL,
  is_active     BOOLEAN DEFAULT TRUE  NOT NULL,
  is_blocked    BOOLEAN DEFAULT FALSE NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
);

-- Upsert admin row with proper timestamps and flags
INSERT INTO "user"(id, telegram_id, username, is_admin, is_active, is_blocked, created_at, updated_at)
VALUES (1, 5254014824, 'admin', TRUE, TRUE, FALSE, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
ON CONFLICT (id) DO UPDATE
   SET telegram_id = EXCLUDED.telegram_id,
       username    = EXCLUDED.username,
       is_admin    = TRUE,
       is_active   = TRUE,
       is_blocked  = FALSE,
       updated_at  = NOW() AT TIME ZONE 'UTC';

-- Optional: basic user_keywords table if not exists
CREATE TABLE IF NOT EXISTS user_keywords(
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  keyword TEXT NOT NULL
);
SQL

echo
echo "===================================================="
echo "✅ ADMIN USER FIX COMPLETED SUCCESSFULLY"
echo "===================================================="
