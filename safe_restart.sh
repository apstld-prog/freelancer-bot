#!/bin/bash
# ==========================================================
# 🚀 SAFE RESTART — RENDER-SAFE (restart μόνο workers)
# ==========================================================
# Δεν ακουμπάει τον server.py (main process του Render).
# Σταματά και ξαναξεκινά ΜΟΝΟ τους workers.
# ==========================================================

set -e
cd "$(dirname "$0")"
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/restart_$(date +'%Y-%m-%d_%H%M').log"

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (Render-Safe Workers)"
echo "=========================================================="
echo "$(date)"
echo

echo "👉 Stopping existing worker processes..."
pkill -f "workers/worker_" || true
sleep 2
echo "✅ Workers stopped."
echo

echo "👉 Starting workers..."
nohup python3 -u workers/worker_freelancer.py >> "$LOG_FILE" 2>&1 &
nohup python3 -u workers/worker_pph.py        >> "$LOG_FILE" 2>&1 &
nohup python3 -u workers/worker_skywalker.py  >> "$LOG_FILE" 2>&1 &
sleep 2

echo "👉 Running workers:"
ps -ef | grep "workers/worker_" | grep -v grep || true
echo
echo "✅ SAFE RESTART COMPLETE — Workers relaunched safely."
echo "Logs saved at $LOG_FILE"
echo "=========================================================="
