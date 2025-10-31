#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (Render-Safe Workers)"
echo "=========================================================="

TIMESTAMP=$(date +"%Y-%m-%d_%H%M")
LOG_DIR="./logs"
LOG_FILE="$LOG_DIR/restart_${TIMESTAMP}.log"

# ensure logs directory
mkdir -p "$LOG_DIR"

{
  echo "$(date)"
  echo
  echo "👉 Stopping existing worker processes..."
  pkill -f "workers/worker_freelancer.py" 2>/dev/null || true
  pkill -f "workers/worker_pph.py" 2>/dev/null || true
  pkill -f "workers/worker_skywalker.py" 2>/dev/null || true
  echo "✅ Workers stopped."
  echo

  echo "👉 Starting new workers..."
  nohup python3 -u workers/worker_freelancer.py > ./logs/worker_freelancer.out 2>&1 &
  nohup python3 -u workers/worker_pph.py > ./logs/worker_pph.out 2>&1 &
  nohup python3 -u workers/worker_skywalker.py > ./logs/worker_skywalker.out 2>&1 &
  echo "✅ Workers started."
  echo

  echo "👉 Checking active processes..."
  ps -ef | grep "workers/" | grep -v grep || true
  echo
  echo "=========================================================="
  echo "✅ SAFE RESTART COMPLETE — Workers relaunched safely."
  echo "Logs saved at $LOG_FILE"
  echo "=========================================================="

} | tee "$LOG_FILE"
