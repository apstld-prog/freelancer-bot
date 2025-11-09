#!/bin/bash
set -e

echo "=========================================================="
echo "ðŸ©º DIAGNOSTIC TOOL â€” FREELANCER BOT"
echo "=========================================================="
date
echo

echo "ðŸ‘‰ Checking environment variables..."
env | grep -E "DATABASE_URL|BOT_TOKEN|ADMIN_IDS|WORKER_INTERVAL" || true
echo

echo "ðŸ‘‰ Checking Python version..."
python3 --version
echo

echo "ðŸ‘‰ Checking installed packages..."
pip freeze | grep -E "fastapi|uvicorn|python-telegram-bot|SQLAlchemy|psycopg2" || true
echo

echo "ðŸ‘‰ Checking directory structure..."
tree -L 3 || ls -R .
echo

echo "ðŸ‘‰ Checking database connectivity..."
python3 - << 'EOF'
from db import test_connection
print("DB connection test:", test_connection())
EOF
echo

echo "ðŸ‘‰ Checking workers..."
ps aux | grep -E "worker_freelancer|worker_pph|worker_skywalker" | grep -v grep || true
echo

echo "ðŸ‘‰ Checking logs..."
ls -lh logs/ || true
echo

echo "âœ… DIAGNOSTIC COMPLETE"
echo "=========================================================="




