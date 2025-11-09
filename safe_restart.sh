#!/bin/bash
set -e

echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT WORKERS"
echo "=========================================================="
date

echo
echo "👉 Detecting running workers..."
pkill -f worker_freelancer.py || true
pkill -f worker_pph.py || true
pkill -f worker_skywalker.py || true
echo "✅ Workers terminated (if any)."

echo
echo "👉 Restarting workers..."
nohup python3 workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python3 workers/worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python3 workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
echo "✅ Workers restarted."

echo
echo "👉 Checking new worker status..."
ps aux | grep worker_ | grep -v grep

echo
echo "=========================================================="
echo "✅ SAFE RESTART COMPLETE — all workers running"
echo "=========================================================="



