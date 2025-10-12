#!/bin/bash
echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
echo "$(date)"
echo "Environment check:"
echo "WORKER_INTERVAL=$WORKER_INTERVAL"
echo "Render Service: freelancer-bot-ns7s"
echo "------------------------------------------------------"

python worker.py &
python server.py
