#!/usr/bin/env bash
# ==========================================================
# 🚀 SAFE RESTART — FREELANCER BOT (workers only, Render-safe)
# ==========================================================
# This script restarts ONLY the background workers.
# Uvicorn/Web server remains managed solely by Render/start.sh.
# ==========================================================

set +e  # keep going even if some pkill finds nothing
date -u
echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT (workers only)"
echo "=========================================================="
echo

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

echo "👉 Terminating existing workers..."
pkill -f "workers/worker_freelancer.py" >/dev/null 2>&1 || true
pkill -f "workers/worker_pph.py"        >/dev/null 2>&1 || true
pkill -f "workers/worker_skywalker.py"  >/dev/null 2>&1 || true
sleep 2
echo "✅ Old workers terminated (if any)."
echo

echo "👉 Starting background workers..."
nohup python3 -u workers/worker_freelancer.py > "$LOG_DIR/worker_freelancer.log" 2>&1 &
nohup python3 -u workers/worker_pph.py        > "$LOG_DIR/worker_pph.log" 2>&1 &
nohup python3 -u workers/worker_skywalker.py  > "$LOG_DIR/worker_skywalker.log" 2>&1 &
sleep 2
echo "✅ Workers running."
echo

echo "ℹ️ Web server (uvicorn) is managed by Render/start.sh — not restarted here."
echo "=========================================================="
echo "✅ SAFE RESTART COMPLETE — Workers refreshed, web stays live"
echo "=========================================================="
