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

# Start new workers
echo "[Worker] Starting background processes..."
python workers/worker_freelancer.py &
python workers/worker_pph.py &
python workers/worker_skywalker.py &

# Start main bot server
echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
python server.py
