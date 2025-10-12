#!/usr/bin/env bash
echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL:-60}"
echo "Render Service: freelancer-bot-ns7s"
echo "------------------------------------------------------"

# Start worker in background
python3 /opt/render/project/src/worker.py &

# Start FastAPI server
exec python3 -m uvicorn server:app --host 0.0.0.0 --port 10000
