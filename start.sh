#!/usr/bin/env bash
set -e

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"
date

echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE}"
echo "Render Service: ${RENDER_SERVICE_NAME:-unknown}"
echo "------------------------------------------------------"

# Start worker
python -u worker.py &

# Start bot
python -u bot.py &

# Start server
exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --log-level info
