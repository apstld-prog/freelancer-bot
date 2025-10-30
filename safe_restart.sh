#!/bin/bash
# ==========================================================
# 🚀 SAFE RESTART SCRIPT — FIXED PORT LOCK ISSUE
# ==========================================================

set -e
cd "$(dirname "$0")"
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restart_$(date +'%Y-%m-%d_%H%M').log"

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (Render, Port Fix)"
echo "=========================================================="
echo "$(date)"
echo

# ----------------------------------------------------------
# Stop any existing uvicorn or workers cleanly
# ----------------------------------------------------------
echo "👉 Stopping running python processes on port 10000..."
fuser -k 10000/tcp || true
pkill -f "python3 -u workers/" || true
sleep 2
echo "✅ Port 10000 freed and workers stopped."
echo

# ----------------------------------------------------------
# Start server.py
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
