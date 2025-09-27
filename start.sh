#!/usr/bin/env bash
set -euo pipefail

echo "[start] launching web(server) + worker..."

# Render sets $PORT automatically; default for local dev.
export PORT="${PORT:-10000}"
export PYTHONUNBUFFERED=1

# 1) Web server (must bind to $PORT)
python -m uvicorn server:app --host 0.0.0.0 --port "$PORT" --log-level info &
SERVER_PID=$!

# 2) Background worker (feeds + notifications)
python worker.py &
WORKER_PID=$!

trap 'echo "[start] terminating children: $SERVER_PID $WORKER_PID"; kill $SERVER_PID $WORKER_PID 2>/dev/null || true' EXIT

# Wait until any child exits; if one dies, exit non-zero to restart
wait -n $SERVER_PID $WORKER_PID
exit $?
