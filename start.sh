#!/bin/bash
# ==========================================================
# 🚀 START SCRIPT — FREELANCER BOT (Render Unified Version)
# ==========================================================
# This script launches server.py, which internally starts:
# - FastAPI + Telegram Bot (webhook)
# - All 3 background workers (Freelancer, PPH, Skywalker)
# ==========================================================

cd "$(dirname "$0")"

echo "=========================================================="
echo "🚀 Starting Freelancer Alert Bot full service"
echo "=========================================================="
date
echo

# Optional: print environment for debug
echo "Environment check:"
echo "WORKER_INTERVAL=${WORKER_INTERVAL:-120}"
echo "KEYWORD_FILTER_MODE=${KEYWORD_FILTER_MODE:-off}"
echo "Render Service: ${RENDER_SERVICE:-freelancer-bot}"
echo "------------------------------------------------------"

# Run unified app (server + workers)
python3 -u server.py
