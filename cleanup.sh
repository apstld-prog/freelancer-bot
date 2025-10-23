#!/usr/bin/env bash
echo "🚀 Starting cleanup of keyword table..."
psql "$DATABASE_URL" -f cleanup_keywords.sql

echo "✅ Cleanup complete!"
echo "Showing remaining keywords:"
psql "$DATABASE_URL" -c "SELECT user_id, keyword FROM keyword;"
