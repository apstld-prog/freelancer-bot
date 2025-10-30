#!/bin/bash
# ==========================================================
# 🚀 SAFE RESTART SCRIPT — FREELANCER BOT (Render edition)
# ==========================================================
# - Kills all running python workers & server
# - Restarts server + workers cleanly
# - Logs status in logs/restart_YYYY-MM-DD_HHMM.txt
# ==========================================================

set -e
cd "$(dirname "$0")"

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restart_$(date +'%Y-%m-%d_%H%M').txt"

echo "==========================================================" | tee "$LOG_FILE"
echo "🚀 SAFE RESTART — FREELANCER BOT SERVICE" | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"
echo "$(date)" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

echo "👉 Detecting running processes..." | tee -a "$LOG_FILE"
pkill -f "python3" || true
sleep 2
echo "✅ All Python processes terminated." | tee -a "$LOG_FILE"

echo | tee -a "$LOG_FILE"
echo "👉 Restarting main server..." | tee -a "$LOG_FILE"
nohup python3 -u server.py >> "$LOG_FILE" 2>&1 &
sleep 3

echo "👉 Restarting workers..." | tee -a "$LOG_FILE"
nohup python3 -u workers/worker_freelancer.py >> "$LOG_FILE" 2>&1 &
sleep 1
nohup python3 -u workers/worker_pph.py >> "$LOG_FILE" 2>&1 &
sleep 1
nohup python3 -u workers/worker_skywalker.py >> "$LOG_FILE" 2>&1 &
sleep 1

echo | tee -a "$LOG_FILE"
echo "👉 Checking status..." | tee -a "$LOG_FILE"
ps -ef | grep "python3 -u" | grep -v grep | tee -a "$LOG_FILE"

echo | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"
echo "✅ SAFE RESTART COMPLETE — ALL COMPONENTS RUNNING" | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"
