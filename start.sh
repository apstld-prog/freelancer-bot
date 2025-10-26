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

# Start workers
echo "[Worker] Starting background processes..."
python workers/worker_freelancer.py &
python workers/worker_pph.py &
python workers/worker_skywalker.py &

# Start main bot server
echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
python server.py
