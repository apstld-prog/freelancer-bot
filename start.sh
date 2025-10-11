#!/usr/bin/env bash
set -euo pipefail

# Respect Render's PORT (defaults to 10000 locally)
export PORT="${PORT:-10000}"

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL:-not_set}"
echo "Render Service: ${RENDER_SERVICE_NAME:-unknown}"
echo "------------------------------------------------------"

# Start worker in background (unbuffered for real-time logs)
echo "[Worker] Launching..."
nohup python -u worker.py > worker.log 2>&1 &
WORKER_PID=$!
echo "[Worker] ✅ Started (PID: $WORKER_PID)"

cleanup() {
  echo "==> stopping..."
  kill -TERM "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM

# Run Uvicorn in foreground so Render detects the open port
echo "[Server] Starting FastAPI + Telegram bot..."
python -m uvicorn server:app --host 0.0.0.0 --port "${PORT}" --no-access-log
