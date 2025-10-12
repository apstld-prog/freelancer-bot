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

# Start background worker (Gorgel)
echo "[Worker] Starting background process..."
python -u worker.py &

# Confirm worker started
sleep 2
pgrep -fa 'python.*worker.py' || echo "[Worker] Warning: process not detected (may have crashed early)"

# Start main FastAPI + Telegram bot
echo "[Server] Starting FastAPI + Telegram bot..."
python -u server.py
