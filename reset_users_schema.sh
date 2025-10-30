#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🧹 RESET USER SCHEMA — FREELANCER ALERT BOT"
echo "=========================================================="
echo
echo "👉 Dropping legacy or corrupted tables..."
psql $DATABASE_URL -c 'DROP TABLE IF EXISTS user_keywords CASCADE;' || true
psql $DATABASE_URL -c 'DROP TABLE IF EXISTS users CASCADE;' || true
psql $DATABASE_URL -c 'DROP TABLE IF EXISTS "user" CASCADE;' || true
psql $DATABASE_URL -c 'DROP TABLE IF EXISTS user_settings CASCADE;' || true
psql $DATABASE_URL -c 'DROP TABLE IF EXISTS user_backup CASCADE;' || true

echo
echo "✅ All old user tables dropped successfully."
echo
echo "👉 Restarting bot to rebuild schema..."
./safe_restart.sh || true

echo
echo "=========================================================="
echo "✅ USER SCHEMA RESET COMPLETE"
echo "=========================================================="
echo "Bot will now recreate tables via ensure_schema() automatically."
echo "You can check logs with: tail -n 50 logs/server.log"
echo
