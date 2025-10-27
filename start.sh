#!/bin/bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date

echo "Environment check:"
echo "FREELANCER_INTERVAL=${FREELANCER_INTERVAL}"
echo "PPH_INTERVAL=${PPH_INTERVAL}"
echo "GREEK_INTERVAL=${GREEK_INTERVAL}"
echo "------------------------------------------------------"

# ------------------------------------------------------
# Cleanup step
# ------------------------------------------------------
echo "[Cleanup] Terminating old worker or server processes..."
pkill -f worker_ || true
pkill -f uvicorn || true
sleep 1
echo "[Cleanup] ✅ Done"

# ------------------------------------------------------
# Init step: ensure directories
# ------------------------------------------------------
if [ ! -d "logs" ]; then
  echo "[Init] Created logs directory"
  mkdir -p logs
fi

if [ ! -d "data" ]; then
  echo "[Init] Created data directory"
  mkdir -p data
fi

# ------------------------------------------------------
# STEP 1: (removed old init scripts)
# ------------------------------------------------------
echo "[Init] Skipping old admin initialization scripts (handled by server.py)"
# python3 init_users.py || echo "⚠️  init_users failed or already ensured."
# python3 init_admin_user.py || echo "⚠️  Admin user init failed or already exists."

# ------------------------------------------------------
# STEP 2: Ensure default keywords
# ------------------------------------------------------
echo "[Init] Ensuring default keywords..."
python3 init_keywords.py || echo "⚠️  Keyword seeding skipped or already done."

# ------------------------------------------------------
# STEP 3: Start background workers
# ------------------------------------------------------
echo "[Worker] Starting background processes..."
python3 workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
python3 workers/worker_pph.py > logs/worker_pph.log 2>&1 &
python3 workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &

sleep 2
echo "[Monitor] Workers are now running in background:"
echo "           - worker_freelancer.py"
echo "           - worker_pph.py"
echo "           - worker_skywalker.py"
echo "------------------------------------------------------"

# ------------------------------------------------------
# STEP 4: Start FastAPI server
# ------------------------------------------------------
echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
python3 -m uvicorn server:app --host 0.0.0.0 --port 10000
