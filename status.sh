#!/bin/bash
# ==========================================================
# ✅ FREELANCER BOT STATUS MONITOR
# ==========================================================

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
NC="\033[0m" # No Color

echo -e "=========================================================="
echo -e "📊 FREELANCER BOT — STATUS CHECK"
echo -e "=========================================================="
echo -e "$(date)"
echo

# --- Check workers ---
check_worker() {
  local name=$1
  if pgrep -f "workers/$name" > /dev/null; then
    echo -e "✅ ${GREEN}$name${NC} is RUNNING"
  else
    echo -e "❌ ${RED}$name${NC} is NOT running"
  fi
}

# --- Check server ---
check_server() {
  if pgrep -f "uvicorn server:app" > /dev/null; then
    echo -e "✅ ${GREEN}Web server${NC} is RUNNING"
  else
    echo -e "❌ ${RED}Web server${NC} is NOT running"
  fi
}

# Run checks
check_worker "worker_freelancer.py"
check_worker "worker_pph.py"
check_worker "worker_skywalker.py"
check_server

echo
echo -e "=========================================================="
echo -e "🩵 Logs (last lines from each worker)"
echo -e "=========================================================="

for w in worker_freelancer worker_pph worker_skywalker; do
  echo -e "\n🔹 ${YELLOW}$w.log${NC}:"
  tail -n 5 "logs/${w}.log" 2>/dev/null || echo "(no log found)"
done

echo -e "\n=========================================================="
echo -e "✅ STATUS CHECK COMPLETE"
echo -e "=========================================================="
