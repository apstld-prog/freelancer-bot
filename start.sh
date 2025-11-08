#!/usr/bin/env bash
# ==========================================================
# ðŸš€ START.SH â€” Freelancer Bot full service (Render stable)
# ==========================================================

set -euo pipefail

echo "======================================================"
echo "ðŸš€ Starting Freelancer Alert Bot full service"
echo "======================================================"
date -u
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL:-180}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE:-on}"
echo "Render Service: ${RENDER_EXTERNAL_URL:-${RENDER_SERVICE_NAME:-unknown}}"
echo "------------------------------------------------------"

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
echo "âœ… Logs directory ready."

# --- Stop stale worker processes ---
echo "ðŸ‘‰ Cleaning any stale workers..."
pkill -f "workers/worker_freelancer.py" >/dev/null 2>&1 || true
pkill -f "workers/worker_pph.py"        >/dev/null 2>&1 || true
pkill -f "workers/worker_skywalker.py"  >/dev/null 2>&1 || true
sleep 2
echo "âœ… Old workers terminated (if any)."

# --- Start background workers ---
echo "ðŸ‘‰ Starting background workers..."
nohup python3 -u workers/worker_freelancer.py > "$LOG_DIR/worker_freelancer.log" 2>&1 &
nohup python3 -u workers/worker_pph.py        > "$LOG_DIR/worker_pph.log" 2>&1 &
nohup python3 -u workers/worker_skywalker.py  > "$LOG_DIR/worker_skywalker.log" 2>&1 &
echo "âœ… Workers running."
echo

# --- Start main FastAPI + Telegram bot (foreground) ---
echo "ðŸ‘‰ Starting FastAPI + Telegram bot via uvicorn..."
PORT="${PORT:-10000}"

# VERY IMPORTANT: run in foreground, single process
exec uvicorn app:app --host 0.0.0.0 --port "${PORT}" --no-access-log --timeout-keep-alive 120

