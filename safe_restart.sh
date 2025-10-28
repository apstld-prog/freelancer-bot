#!/bin/bash
echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT WORKERS"
echo "=========================================================="
date

# Step 1 — kill old workers
echo
echo "👉 Detecting running workers..."
pkill -f worker_ || true
sleep 2
echo "✅ Workers terminated (if any)."

# Step 2 — recreate logs
mkdir -p logs

# Step 3 — restart all workers cleanly
echo
echo "👉 Restarting workers..."
nohup python3 -u workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python3 -u workers/worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python3 -u workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
sleep 3

# Step 4 — verify
echo
echo "👉 Checking new worker status..."
ps aux | grep worker_ | grep -v grep

echo
echo "=========================================================="
echo "✅ SAFE RESTART COMPLETE — all workers relaunched."
echo "=========================================================="
