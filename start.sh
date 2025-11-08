#!/usr/bin/env bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date
echo "Environment check:"
echo "WORKER_INTERVAL=$WORKER_INTERVAL"
echo "KEYWORD_FILTER_MODE=$KEYWORD_FILTER_MODE"
echo "Render Service: $RENDER_EXTERNAL_URL"
echo "------------------------------------------------------"

mkdir -p logs
echo "✅ Logs directory ready."

echo "👉 Cleaning any stale workers..."
pkill -f worker_freelancer.py || true
pkill -f worker_pph.py || true
pkill -f worker_skywalker.py || true
echo "✅ Old workers terminated (if any)."

echo "👉 Starting background workers..."
nohup python3 workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python3 workers/worker_pph.py        > logs/worker_pph.log 2>&1 &
nohup python3 workers/worker_skywalker.py  > logs/worker_skywalker.log 2>&1 &
echo "✅ Workers running."

echo "👉 Starting FastAPI + Telegram bot via uvicorn..."
exec uvicorn server:app --host 0.0.0.0 --port 10000
