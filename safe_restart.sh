#!/bin/bash
echo "=========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT WORKERS"
echo "=========================================================="
date

cd ~/project/src || exit 1

echo
echo "👉 Detecting running workers..."
ps aux | grep 'worker_' | grep -v grep

echo
echo "👉 Terminating old workers..."
pkill -f 'worker_' && echo "✅ Workers terminated." || echo "ℹ️ No old workers running."

echo
echo "👉 Restarting workers..."
nohup python3 -u workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python3 -u workers/worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python3 -u workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
sleep 3

echo
echo "👉 Checking new worker status..."
ps aux | grep 'worker_' | grep -v grep

echo
echo "=========================================================="
echo "✅ SAFE RESTART COMPLETE — all workers relaunched"
echo "=========================================================="
