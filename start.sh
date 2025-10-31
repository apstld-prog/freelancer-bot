#!/bin/bash
# ==========================================================
# 🚀 START SCRIPT — FREELANCER BOT (Render, separate workers)
# ==========================================================
# Ξεκινά πρώτα τους 3 workers (nohup, background) και μετά
# τρέχει σε foreground τον server.py (FastAPI + Telegram).
# ==========================================================

cd "$(dirname "$0")"

echo "=========================================================="
echo "🚀 Starting Freelancer Alert Bot full service"
echo "=========================================================="
date
echo
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL:-180}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE:-on}"
echo "Render Service: ${RENDER_SERVICE:-freelancer-bot}"
echo "------------------------------------------------------"

# Start workers (background, detached)
nohup python3 -u workers/worker_freelancer.py >/dev/null 2>&1 &
nohup python3 -u workers/worker_pph.py        >/dev/null 2>&1 &
nohup python3 -u workers/worker_skywalker.py  >/dev/null 2>&1 &

# Start FastAPI + Telegram bot (foreground/main)
python3 -u server.py
