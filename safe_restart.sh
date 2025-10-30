#!/bin/bash
# ==========================================================
# 🚀 SAFE RESTART SCRIPT — UNIVERSAL FIX (no fuser)
# ==========================================================

set -e
cd "$(dirname "$0")"
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restart_$(date +'%Y-%m-%d_%H%M').log"

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (Universal Port Fix)"
echo "=========================================================="
echo "$(date)"
echo

# ----------------------------------------------------------
# Kill previous processes cleanly
# ----------------------------------------------------------
echo "👉 Stopping previous python processes..."
pkill -f "server.py" || true
pkill -f "uvicorn" || true
pkill -f "workers/worker_" || true
sleep 2
echo "✅ Previous processes terminated."
echo

# ----------------------------------------------------------
# Start server
# ----------------------------------------------------------
echo "👉 Starting server.py..."
nohup python3 -u server.py >> "$LOG_FILE" 2>&1 &
disown
sleep 5

# ----------------------------------------------------------
# Start workers
# ----------------------------------------------------------
echo "👉 Starting workers..."
nohup python3 -u workers/worker_freelancer.py >> "$LOG_FILE" 2>&1 &
disown
sleep 1
nohup python3 -u workers/worker_pph.py >> "$LOG_FILE" 2>&1 &
disown
sleep 1
nohup python3 -u workers/worker_skywalker.py >> "$LOG_FILE" 2>&1 &
disown
sleep 2

# ----------------------------------------------------------
# Verify
# ----------------------------------------------------------
echo "👉 Checking running processes..."
ps -ef | grep "python3 -u" | grep -v grep
echo

echo "✅ SAFE RESTART COMPLETE — all components relaunched."
echo "Logs saved at $LOG_FILE"
echo "=========================================================="
