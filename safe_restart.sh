#!/bin/bash
set -e

echo "=========================================================="
echo "ðŸš€ SAFE RESTART â€” FREELANCER BOT WORKERS"
echo "=========================================================="
date

echo
echo "ðŸ‘‰ Detecting running workers..."
pkill -f worker_freelancer.py || true
pkill -f worker_pph.py || true
pkill -f worker_skywalker.py || true
echo "âœ… Workers terminated (if any)."

echo
echo "ðŸ‘‰ Restarting workers..."
nohup python3 workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python3 workers/worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python3 workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
echo "âœ… Workers restarted."

echo
echo "ðŸ‘‰ Checking new worker status..."
ps aux | grep worker_ | grep -v grep

echo
echo "=========================================================="
echo "âœ… SAFE RESTART COMPLETE â€” all workers running"
echo "=========================================================="




