#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (Render-Safe Workers)"
echo "=========================================================="
echo "$(date -u)"

cd ~/project/src

# Ensure logs directory exists (persistent)
mkdir -p ~/project/src/logs
LOGFILE="~/project/src/logs/restart_$(date -u +%Y-%m-%d_%H%M).log"

echo "👉 Stopping existing worker processes..."
pkill -f "python3 -u workers/" || true
echo "✅ Workers stopped." | tee -a $LOGFILE

echo "" | tee -a $LOGFILE
echo "👉 Starting workers..." | tee -a $LOGFILE

# Start all worker scripts
nohup python3 -u workers/worker_freelancer.py >> ~/project/src/logs/worker_freelancer.log 2>&1 &
nohup python3 -u workers/worker_pph.py >> ~/project/src/logs/worker_pph.log 2>&1 &
nohup python3 -u workers/worker_skywalker.py >> ~/project/src/logs/worker_skywalker.log 2>&1 &

sleep 3
echo "👉 Running workers:" | tee -a $LOGFILE
ps aux | grep "python3 -u workers/" | grep -v grep | tee -a $LOGFILE

echo "" | tee -a $LOGFILE
echo "✅ SAFE RESTART COMPLETE — Workers relaunched safely." | tee -a $LOGFILE
echo "Logs saved at $LOGFILE"
echo "=========================================================="

# Optional health check
echo "👉 Checking FastAPI health endpoint..."
if curl -fsS http://127.0.0.1:10000/health >/dev/null 2>&1; then
  echo "✅ FastAPI service is healthy" | tee -a $LOGFILE
else
  echo "⚠️ Health check failed or endpoint not available" | tee -a $LOGFILE
fi
