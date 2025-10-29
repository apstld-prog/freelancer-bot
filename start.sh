#!/bin/bash
set -euo pipefail
trap 'echo "⚠️  Deployment script failed on line $LINENO" >&2' ERR

echo "======================================================"
echo "🚀 Starting Freelancer Alert Bot full service"
echo "======================================================"

date
echo "Environment check:"
echo "FREELANCER_INTERVAL=${FREELANCER_INTERVAL:-60}"
echo "PPH_INTERVAL=${PPH_INTERVAL:-300}"
echo "GREEK_INTERVAL=${GREEK_INTERVAL:-300}"
echo "------------------------------------------------------"

# Cleanup old processes safely
echo "[Cleanup] Terminating old worker or server processes..."
pkill -f "worker_freelancer.py" 2>/dev/null || true
pkill -f "worker_pph.py" 2>/dev/null || true
pkill -f "worker_skywalker.py" 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true
echo "[Cleanup] ✅ Done"

# Ensure logs directory
mkdir -p logs
echo "[Init] Created logs directory"

# Ensure users
echo "[Init] Ensuring users (admin & defaults)..."
python3 init_users.py || true
python3 init_admin_user.py || true

# Ensure default keywords
echo "[Init] Ensuring default keywords..."
python3 db_keywords.py || true

echo "======================================================"
echo "🔑 INIT KEYWORDS TOOL — ensure default admin keywords"
echo "======================================================"
echo "✅ Default keywords ensured successfully."
echo "======================================================"

# Start background workers
echo "[Worker] Starting background processes..."
nohup python3 -u workers/worker_freelancer.py > logs/worker_freelancer.log 2>&1 &
nohup python3 -u workers/worker_pph.py > logs/worker_pph.log 2>&1 &
nohup python3 -u workers/worker_skywalker.py > logs/worker_skywalker.log 2>&1 &
echo "[Monitor] Workers are now running in background:"
echo "           - worker_freelancer.py"
echo "           - worker_pph.py"
echo "           - worker_skywalker.py"
echo "------------------------------------------------------"

# Start main FastAPI server (blocking)
echo "[Server] Starting FastAPI + Telegram bot via uvicorn..."
python3 -m uvicorn server:app --host 0.0.0.0 --port 10000 --proxy-headers --forwarded-allow-ips='*'

echo "======================================================"
echo "✅ Freelancer Bot startup sequence completed successfully"
echo "======================================================"

exit 0
