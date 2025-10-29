#!/bin/bash
# ============================================
# 🧠 AUTO-FIX ADMIN USER IN FREELANCER BOT DB
# ============================================

echo "===================================================="
echo "🔧 AUTO-FIX: ADMIN USER IN POSTGRES DATABASE"
echo "===================================================="
echo ""

if [ -z "$DATABASE_URL" ]; then
  echo "❌ DATABASE_URL environment variable not set!"
  echo "➡️ Please export it first: export DATABASE_URL=postgres://..."
  exit 1
fi

echo "👉 Connecting to PostgreSQL..."
psql "$DATABASE_URL" <<'SQL'
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT,
    username TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    is_blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO "user" (id, telegram_id, username, is_admin, is_active, is_blocked, created_at)
VALUES (1, 5254014824, 'admin', TRUE, TRUE, FALSE, NOW())
ON CONFLICT (id) DO UPDATE
SET telegram_id = EXCLUDED.telegram_id,
    username = EXCLUDED.username,
    is_admin = TRUE,
    is_active = TRUE,
    is_blocked = FALSE;

SELECT id, telegram_id, username, is_admin, is_active, is_blocked
FROM "user"
WHERE id = 1;
SQL

echo ""
echo "===================================================="
echo "✅ ADMIN USER FIX COMPLETED SUCCESSFULLY"
echo "===================================================="
echo ""
