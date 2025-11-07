#!/bin/bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date

echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE}"
echo "Render Service: https://${RENDER_EXTERNAL_HOSTNAME}"
echo "------------------------------------------------------"

# Kill any stale workers
echo "✅ Logs directory ready."
mkdir -p logs

echo "👉 Cleaning any stale workers..."
pkill -f worker_freelancer.py || true
pkill -f worker_pph.py || true
pkill -f worker_skywalker.py || true
echo "✅ Old workers terminated (if any)."

# Start workers
echo "👉 Starting background workers..."
python3 workers/worker_freelancer.py >> logs/freelancer.log 2>&1 &
python3 workers/worker_pph.py >> logs/pph.log 2>&1 &
python3 workers/worker_skywalker.py >> logs/skywalker.log 2>&1 &
echo "✅ Workers running."

# Start API + Bot
echo "👉 Starting FastAPI + Telegram bot via uvicorn..."
python3 -m uvicorn app:app --host 0.0.0.0 --port 10000
