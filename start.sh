#!/bin/bash
echo "======================================================"
echo "🚀 Starting Modular Freelancer Alert Bot"
echo "======================================================"
date

# Load environment variables
export $(grep -v '^#' .env | xargs)

echo "Environment check:"
echo "FREELANCER_INTERVAL=$FREELANCER_INTERVAL"
echo "PPH_INTERVAL=$PPH_INTERVAL"
echo "GREEK_INTERVAL=$GREEK_INTERVAL"
echo "------------------------------------------------------"

# Start each worker in background
python3 workers/worker_freelancer.py &
python3 workers/worker_pph.py &
python3 workers/worker_skywalker.py &

# Finally start the main server (Telegram bot)
python3 server.py
