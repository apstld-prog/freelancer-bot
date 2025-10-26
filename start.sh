#!/bin/bash
echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date

echo "Environment check:"
echo "FREELANCER_INTERVAL=${FREELANCER_INTERVAL:-60}"
echo "PPH_INTERVAL=${PPH_INTERVAL:-300}"
echo "GREEK_INTERVAL=${GREEK_INTERVAL:-300}"
echo "------------------------------------------------------"

# Kill any old processes that might still be running
echo "[Cleanup] Terminating old worker or server processes..."
pkill -f worker_freelancer.py 2>/dev/null
pkill -f worker_pph.py 2>/dev/null
pkill -f worker_skywalker.py 2>/dev/null
pkill -f server.py 2>/dev/null
sleep 2

# Create logs folder if it doesn’t exist
if [ ! -d "logs" ]; then
  mkdir logs
  echo "[Init] Created logs directory"
fi

# Start new workers with nohup to persist across restarts
echo "[Worker] Starting background processes..."
nohup python workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python workers/worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &

# Log monitoring info
echo "[Monitor] Workers are now running in background:"
echo "           - worker_freelancer.py (log: logs/worker_freelancer.log)"
echo "           - worker_pph.py        (log: logs/worker_pph.log)"
echo "           - worker_skywalker.py  (log: logs/worker_skywalker.log)"
echo "------------------------------------------------------"

# Start the FastAPI + Telegram bot in foreground (so Render stays active)
echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
exec python -m uvicorn server:app --host 0.0.0.0 --port 10000 --no-access-log

