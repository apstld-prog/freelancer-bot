#!/usr/bin/env bash
set -e

export PYTHONUNBUFFERED=1

echo "==> launching web(server) + worker..."
# web (FastAPI + PTB webhook)
uvicorn server:app --host 0.0.0.0 --port 10000 &
WEB_PID=$!

# worker (scraper loop)
python -u worker.py &
W_PID=$!

wait $WEB_PID
kill $W_PID || true
