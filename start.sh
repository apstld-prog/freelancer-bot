#!/usr/bin/env bash
set -euo pipefail

# Respect Render's PORT (defaults to 10000 locally)
export PORT="${PORT:-10000}"

echo "==> launching web(server) + worker..."

# Start worker runner in background
python -u worker_runner.py &
WORKER_PID=$!

cleanup() {
  echo "==> stopping..."
  kill -TERM "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM

# Run Uvicorn in foreground so Render detects the open port
python -m uvicorn server:app --host 0.0.0.0 --port "${PORT}" --no-access-log --log-level info
