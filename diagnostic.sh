#!/bin/bash
set -e

echo "=========================================================="
echo "🩺 DIAGNOSTIC TOOL — FREELANCER BOT"
echo "=========================================================="
date
echo

echo "👉 Checking environment variables..."
env | grep -E "DATABASE_URL|BOT_TOKEN|ADMIN_IDS|WORKER_INTERVAL" || true
echo

echo "👉 Checking Python version..."
python3 --version
echo

echo "👉 Checking installed packages..."
pip freeze | grep -E "fastapi|uvicorn|python-telegram-bot|SQLAlchemy|psycopg2" || true
echo

echo "👉 Checking directory structure..."
tree -L 3 || ls -R .
echo

echo "👉 Checking database connectivity..."
python3 - << 'EOF'
from db import test_connection
print("DB connection test:", test_connection())
EOF
echo

echo "👉 Checking workers..."
ps aux | grep -E "worker_freelancer|worker_pph|worker_skywalker" | grep -v grep || true
echo

echo "👉 Checking logs..."
ls -lh logs/ || true
echo

echo "✅ DIAGNOSTIC COMPLETE"
echo "=========================================================="

