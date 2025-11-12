#!/usr/bin/env bash
set -e
echo "======================================================"
echo "Starting Freelancer Alert Bot full service"
echo "======================================================"
date -u
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE}"
echo "Render Service: ${RENDER_EXTERNAL_URL}"
echo "------------------------------------------------------"
echo "[*] Starting FastAPI + Telegram bot via uvicorn..."
exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}
