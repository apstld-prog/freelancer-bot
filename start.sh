#!/usr/bin/env bash
set -euo pipefail

echo "Starting health server..."
python -m uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}" &
SERVER_PID=$!

echo "Starting Telegram bot..."
python bot.py &
BOT_PID=$!

echo "Starting worker..."
python worker.py &
WORKER_PID=$!

cleanup() {
  echo "Shutting down..."
  kill "$WORKER_PID" "$BOT_PID" "$SERVER_PID" 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM

# If any child exits, stop all
wait -n
cleanup
wait
