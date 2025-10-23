#!/usr/bin/env bash
echo "🚀 Starting cleanup of keyword table..."

# Σύνδεση στη remote PostgreSQL βάση με το πλήρες URL
psql "$DATABASE_URL" -f cleanup_keywords.sql --set=sslmode=require

echo "✅ Cleanup complete!"
echo "Showing remaining keywords:"
psql "$DATABASE_URL" -c "SELECT user_id, keyword FROM keyword;" --set=sslmode=require
