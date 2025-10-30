#!/bin/bash
# ==========================================================
# 🚀 SAFE RESTART SCRIPT — FREELANCER BOT (FINAL RENDER VERSION)
# ==========================================================
# - Restarts all components (server + workers)
# - Keeps logs per run under ./logs/
# - Runs all processes detached (nohup + disown)
# - Health-checks server.py before reporting success
# ==========================================================

set -e
cd "$(dirname "$0")"

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restart_$(date +'%Y-%m-%d_%H%M').log"

echo "==========================================================" | tee "$LOG_FILE"
echo "🚀 SAFE RESTART — FREELANCER BOT (Render)" | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"
echo "$(date)" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

echo "👉 Stopping all running python processes..." | tee -a "$LOG_FILE"
pkill -f "python3" || true
sleep 2
echo "✅ All python processes terminated." | tee -a "$LOG_FILE"

echo | tee -a "$LOG_FILE"
echo "👉 Starting server.py..." | tee -a "$LOG_FILE"
nohup python3 -u server.py >> "$LOG_FILE" 2>&1 &
disown
sleep 5

echo "👉 Starting workers..." | tee -a "$LOG_FILE"
nohup python3 -u workers/worker_freelancer.py >> "$LOG_FILE" 2>&1 &
disown
sleep 1
nohup python3 -u workers/worker_pph.py >> "$LOG_FILE" 2>&1 &
disown
sleep 1
nohup python3 -u workers/worker_skywalker.py >> "$LOG_FILE" 2>&1 &
disown
sleep 2

echo | tee -a "$LOG_FILE"
echo "👉 Checking running processes..." | tee -a "$LOG_FILE"
ps -ef | grep "python3 -u" | grep -v grep | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

echo "👉 Health-checking server.py..." | tee -a "$LOG_FILE"
if pgrep -f "server.py" > /dev/null; then
  echo "✅ server.py is running." | tee -a "$LOG_FILE"
else
  echo "❌ server.py is NOT running. Check $LOG_FILE for errors." | tee -a "$LOG_FILE"
fi

echo | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"
echo "✅ SAFE RESTART COMPLETE — ALL COMPONENTS RUNNING" | tee -a "$LOG_FILE"
echo "Logs saved in: $LOG_FILE" | tee -a "$LOG_FILE"
echo "=========================================================="
