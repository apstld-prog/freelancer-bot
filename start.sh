#!/usr/bin/env bash
set -euo pipefail

# Respect Render's PORT (falls back to 10000 locally)
export PORT="${PORT:-10000}"

echo "==> launching web(server) + worker..."

# Start worker in background (logs πάμε στο stdout)
python -u worker.py &
WORKER_PID=$!

# When container receives SIGTERM/SIGINT, kill background worker too
cleanup() {
  echo "==> stopping..."
  kill -TERM "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM

# Start Uvicorn in foreground so Render βλέπει το open port
# IMPORTANT: bind to 0.0.0.0:$PORT
python -m uvicorn server:app --host 0.0.0.0 --port "${PORT}" --no-access-log
