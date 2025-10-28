#!/bin/bash
# ==========================================================
# 🧠 FREELANCER BOT SAFE RESTART TOOL
# ==========================================================
# Safely restarts only the background workers without killing uvicorn or FastAPI.
# Use this instead of pkill -f python to avoid Render reconnect loops.
# ==========================================================

echo "==========================================================="
echo "🚀 SAFE RESTART — FREELANCER BOT WORKERS"
echo "==========================================================="
date -u
echo

# Step 1 — detect worker processes
echo "👉 Detecting running workers..."
WORKERS=$(ps aux | grep "worker_" | grep -v grep | awk '{print $2}')
if [ -z "$WORKERS" ]; then
  echo "⚠️ No active worker processes found."
else
  echo "🧹 Killing existing workers..."
  for PID in $WORKERS; do
    echo "   → Killing PID $PID"
    kill -9 $PID || true
  done
fi

# Step 2 — short pause
sleep 3
echo "✅ Workers terminated (if any)."
echo

# Step 3 — restart all workers cleanly
echo "👉 Restarting workers..."
nohup python -u worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python -u worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python -u worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
sleep 2

# Step 4 — verify processes are up
echo
echo "👉 Checking new worker status..."
ps aux | grep worker_ | grep -v grep
echo
echo "==========================================================="
echo "✅ SAFE RESTART COMPLETE — all workers relaunched."
echo "==========================================================="
