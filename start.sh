#!/bin/bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date -u
echo "Environment check:"
echo "FREELANCER_INTERVAL=${FREELANCER_INTERVAL}"
echo "PPH_INTERVAL=${PPH_INTERVAL}"
echo "GREEK_INTERVAL=${GREEK_INTERVAL}"
echo "------------------------------------------------------"

# Cleanup
echo "[Cleanup] Terminating old worker or server processes..."
pkill -f worker_freelancer.py 2>/dev/null || true
pkill -f worker_pph.py 2>/dev/null || true
pkill -f worker_skywalker.py 2>/dev/null || true
pkill -f uvicorn 2>/dev/null || true
pkill -f server.py 2>/dev/null || true
echo "[Cleanup] ✅ Done"
echo

mkdir -p logs
echo "[Init] Created logs directory"

echo "[Init] Ensuring default keywords..."
python3 init_keywords.py || true

echo "[Worker] Starting background processes..."
python3 workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
python3 workers/worker_pph.py > logs/worker_pph.log 2>&1 &
python3 workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
sleep 2
echo "[Monitor] Workers are now running in background:"
echo "           - worker_freelancer.py"
echo "           - worker_pph.py"
echo "           - worker_skywalker.py"
echo "------------------------------------------------------"

echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
python3 -m uvicorn server:app --host 0.0.0.0 --port 10000
