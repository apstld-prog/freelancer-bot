#!/bin/bash
set -e

echo "Starting workers..."
python3 -u workers/worker_freelancer.py &
python3 -u workers/worker_pph.py &
python3 -u workers/worker_skywalker.py &

echo "Starting Telegram bot..."
python3 -u bot.py &

echo "Starting FastAPI server..."
exec uvicorn server:app --host 0.0.0.0 --port ${PORT}

