#!/usr/bin/env bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date

# Load environment
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL:-120}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE:-on}"
echo "Render Service: ${RENDER_SERVICE_NAME:-unknown}"
echo "------------------------------------------------------"

# Ensure python path inside project
cd /opt/render/project/src || exit 1

# Start the worker in background
echo "[Worker] Starting background process..."
nohup python3 worker.py > worker.log 2>&1 &
WORKER_PID=$!
sleep 3
if ps -p $WORKER_PID > /dev/null; then
    echo "[Worker] ✅ Running (PID: $WORKER_PID)"
else
    echo "[Worker] ❌ Failed to start!"
    cat worker.log || true
    exit 1
fi

# Start the FastAPI/Telegram bot (main server)
echo "[Server] Starting FastAPI + Telegram bot..."
exec python3 server.py
