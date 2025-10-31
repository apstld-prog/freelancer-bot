#!/usr/bin/env bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date
echo "Environment check:"
echo "WORKER_INTERVAL=$WORKER_INTERVAL"
echo "KEYWORD_FILTER_MODE=$KEYWORD_FILTER_MODE"
echo "Render Service: freelancer-bot-ns7s"
echo "------------------------------------------------------"

echo "[Worker] Starting background processes..."
python3 -u workers/worker_freelancer.py &
python3 -u workers/worker_pph.py &
python3 -u workers/worker_skywalker.py &
echo "[Worker] ✅ Workers running in background."

echo "[Server] Starting FastAPI + Telegram bot..."
exec python3 -u server.py
