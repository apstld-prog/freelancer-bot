#!/usr/bin/env bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date

echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE}"
echo "Render Service: ${RENDER_SERVICE_NAME:-unknown}"
echo "------------------------------------------------------"

# 1️⃣ Start background worker (Gorgel)
echo "[Worker] Starting background process..."
python -u worker.py &
sleep 2
pgrep -fa 'python.*worker.py' || echo "[Worker] Warning: process not detected (may have crashed early)"

# 2️⃣ Start main FastAPI + Telegram bot via uvicorn (Render web process)
echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --log-level info
