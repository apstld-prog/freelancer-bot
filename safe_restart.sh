#!/bin/bash
# ==========================================================
# 🚀 SAFE RESTART — RENDER-SAFE VERSION (no kill of main)
# ==========================================================

set -e
cd "$(dirname "$0")"
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restart_$(date +'%Y-%m-%d_%H%M').log"

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (Render-Safe)"
echo "=========================================================="
echo "$(date)"
echo

# ----------------------------------------------------------
# Kill only worker processes (NOT the main FastAPI server)
# ----------------------------------------------------------
echo "👉 Stopping existing worker processes..."
pkill -f "workers/worker_" || true
sleep 2
echo "✅ Workers stopped."
echo

# ----------------------------------------------------------
# Start workers again (server.py left untouched)
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
# Verify processes
# ----------------------------------------------------------
echo "👉 Checking running processes..."
ps -ef | grep "python3 -u workers" | grep -v grep
echo
echo "✅ SAFE RESTART COMPLETE — Workers relaunched safely."
echo "Logs saved at $LOG_FILE"
echo "=========================================================="
